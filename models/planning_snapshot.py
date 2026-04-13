from odoo import models, fields, api, _
from odoo.exceptions import UserError
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)


class PlanningSnapshot(models.Model):
    _name = 'planning.snapshot'
    _description = 'Snapshot de Planificación de Producción'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nombre', required=True, tracking=True,
                        default=lambda self: _('Nuevo'))
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('generated', 'Demanda Generada'),
        ('exploded', 'BOM Explotada'),
        ('done', 'Finalizado'),
        ('cancelled', 'Cancelado'),
    ], string='Estado', default='draft', tracking=True, index=True)

    date_from = fields.Date(string='Fecha Desde', tracking=True)
    date_to = fields.Date(string='Fecha Hasta', tracking=True)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Almacenes', tracking=True)
    partner_ids = fields.Many2many('res.partner', string='Clientes (filtro)')
    product_ids = fields.Many2many('product.product', string='Productos (filtro)')

    # Líneas
    demand_line_ids = fields.One2many('planning.demand.line', 'snapshot_id', string='Líneas de Demanda')
    explosion_line_ids = fields.One2many('planning.bom.explosion.line', 'snapshot_id', string='Explosión BOM')
    consolidated_line_ids = fields.One2many('planning.bom.consolidated', 'snapshot_id', string='Demanda Consolidada')

    # Conteos
    demand_count = fields.Integer(compute='_compute_counts', string='Líneas Demanda')
    explosion_count = fields.Integer(compute='_compute_counts', string='Líneas Explosión')
    consolidated_count = fields.Integer(compute='_compute_counts', string='Líneas Consolidadas')

    # KPIs
    total_demand_value = fields.Float(string='Valor Total Demanda', compute='_compute_kpis', store=False)
    total_products = fields.Integer(string='Productos Únicos', compute='_compute_kpis', store=False)
    total_orders = fields.Integer(string='Órdenes Únicas', compute='_compute_kpis', store=False)
    critical_items_count = fields.Integer(string='Items Críticos (stock < 50%)', compute='_compute_kpis', store=False)

    notes = fields.Html(string='Notas')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('planning.snapshot') or _('Nuevo')
        return super().create(vals_list)

    @api.depends('demand_line_ids', 'explosion_line_ids', 'consolidated_line_ids')
    def _compute_counts(self):
        for rec in self:
            rec.demand_count = len(rec.demand_line_ids)
            rec.explosion_count = len(rec.explosion_line_ids)
            rec.consolidated_count = len(rec.consolidated_line_ids)

    @api.depends('demand_line_ids', 'consolidated_line_ids')
    def _compute_kpis(self):
        for rec in self:
            rec.total_demand_value = sum(rec.demand_line_ids.mapped('product_uom_qty'))
            rec.total_products = len(set(rec.demand_line_ids.mapped('product_id.id')))
            rec.total_orders = len(set(rec.demand_line_ids.mapped('sale_order_id.id')))
            rec.critical_items_count = len(rec.consolidated_line_ids.filtered(
                lambda l: l.coverage_pct < 50
            ))

    def action_generate_demand(self):
        """Genera las líneas de demanda desde órdenes de venta confirmadas."""
        self.ensure_one()
        if self.state not in ('draft', 'generated'):
            raise UserError(_('Solo se puede generar demanda en estado Borrador o Demanda Generada.'))

        # Limpiar líneas previas
        self.demand_line_ids.unlink()
        self.explosion_line_ids.unlink()
        self.consolidated_line_ids.unlink()

        domain = [
            ('state', 'in', ['sale', 'done']),
        ]

        if self.date_from:
            domain.append(('commitment_date', '>=', fields.Datetime.to_datetime(self.date_from)))
        if self.date_to:
            domain.append(('commitment_date', '<=', fields.Datetime.to_datetime(self.date_to)))
        if self.warehouse_ids:
            domain.append(('warehouse_id', 'in', self.warehouse_ids.ids))
        if self.partner_ids:
            domain.append(('order_id.partner_id', 'in', self.partner_ids.ids))
        if self.product_ids:
            domain.append(('product_id', 'in', self.product_ids.ids))

        # Solo productos con demanda pendiente
        sale_lines = self.env['sale.order.line'].search(domain)
        sale_lines = sale_lines.filtered(lambda l: l.product_uom_qty > l.qty_delivered and l.product_id.type in ('consu', 'product'))

        vals_list = []
        for sl in sale_lines:
            so = sl.order_id
            vals_list.append({
                'snapshot_id': self.id,
                'sale_order_id': so.id,
                'sale_order_name': so.name,
                'partner_id': so.partner_id.id,
                'partner_number': so.partner_id.ref or '',
                'warehouse_id': so.warehouse_id.id,
                'product_id': sl.product_id.id,
                'product_description': sl.name,
                'product_uom_qty': sl.product_uom_qty,
                'qty_delivered': sl.qty_delivered,
                'product_uom_id': sl.product_uom.id,
                'commitment_date': so.commitment_date or so.date_order,
                'order_date': so.date_order,
                'state': so.state,
                'sale_line_id': sl.id,
                'activity_note': '',
            })

        if vals_list:
            self.env['planning.demand.line'].create(vals_list)

        self.state = 'generated'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Demanda Generada'),
                'message': _('%d líneas de demanda creadas.') % len(vals_list),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_explode_bom(self):
        """Explota las listas de materiales multinivel para cada producto con demanda."""
        self.ensure_one()
        if self.state not in ('generated', 'exploded'):
            raise UserError(_('Primero debe generar la demanda.'))

        self.explosion_line_ids.unlink()
        self.consolidated_line_ids.unlink()

        # Agrupar demanda por producto y almacén
        demand_by_product_wh = defaultdict(lambda: {'qty': 0, 'orders': set()})
        for dl in self.demand_line_ids:
            key = (dl.product_id.id, dl.warehouse_id.id)
            demand_by_product_wh[key]['qty'] += dl.qty_pending
            demand_by_product_wh[key]['orders'].add(dl.sale_order_name)

        explosion_vals = []
        # Para consolidación
        consolidated_data = defaultdict(lambda: {
            'qty': 0, 'finished_products': set(), 'orders': set(), 'lines': 0
        })

        for (product_id, warehouse_id), data in demand_by_product_wh.items():
            product = self.env['product.product'].browse(product_id)
            warehouse = self.env['stock.warehouse'].browse(warehouse_id)
            demand_qty = data['qty']
            order_names = ', '.join(sorted(data['orders']))

            # Explosionar recursivamente
            self._explode_product_bom(
                explosion_vals, consolidated_data,
                product, product, warehouse,
                demand_qty, 1.0, 0, order_names
            )

        if explosion_vals:
            self.env['planning.bom.explosion.line'].create(explosion_vals)

        # Crear líneas consolidadas
        consolidated_vals = []
        for (prod_id, wh_id, ptype), cdata in consolidated_data.items():
            product = self.env['product.product'].browse(prod_id)
            consolidated_vals.append({
                'snapshot_id': self.id,
                'product_id': prod_id,
                'product_type': ptype,
                'product_uom_id': product.uom_id.id,
                'warehouse_id': wh_id,
                'total_required': cdata['qty'],
                'finished_product_names': ', '.join(sorted(cdata['finished_products'])),
                'sale_order_names': ', '.join(sorted(cdata['orders'])),
                'demand_line_count': cdata['lines'],
            })

        if consolidated_vals:
            self.env['planning.bom.consolidated'].create(consolidated_vals)

        self.state = 'exploded'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('BOM Explotada'),
                'message': _('%d líneas de explosión, %d consolidadas.') % (
                    len(explosion_vals), len(consolidated_vals)),
                'type': 'success',
                'sticky': False,
            }
        }

    def _explode_product_bom(self, explosion_vals, consolidated_data,
                              finished_product, current_product, warehouse,
                              demand_qty, cumulative_factor, level, order_names,
                              parent_product=None, visited=None):
        """Explosión recursiva de BOM multinivel."""
        if visited is None:
            visited = set()

        if current_product.id in visited:
            _logger.warning("BOM circular detectada para producto %s", current_product.display_name)
            return
        visited = visited | {current_product.id}

        # Buscar BOM del producto actual
        bom = self.env['mrp.bom']._bom_find(current_product, company_id=self.env.company.id)
        if isinstance(bom, dict):
            bom = bom.get(current_product, self.env['mrp.bom'])

        has_bom = bool(bom)

        # Determinar tipo
        if level == 0:
            product_type = 'finished'
        elif has_bom:
            product_type = 'semi'
        else:
            product_type = 'raw'

        qty_required = demand_qty * cumulative_factor

        # Agregar línea de explosión
        explosion_vals.append({
            'snapshot_id': self.id,
            'finished_product_id': finished_product.id,
            'product_id': current_product.id,
            'product_type': product_type,
            'bom_id': bom.id if has_bom else False,
            'bom_level': level,
            'parent_product_id': parent_product.id if parent_product else False,
            'qty_per_unit': cumulative_factor,
            'demand_qty_finished': demand_qty,
            'qty_required': qty_required,
            'product_uom_id': current_product.uom_id.id,
            'warehouse_id': warehouse.id,
            'sale_order_ids': order_names,
        })

        # Consolidar
        ckey = (current_product.id, warehouse.id, product_type)
        consolidated_data[ckey]['qty'] += qty_required
        consolidated_data[ckey]['finished_products'].add(finished_product.display_name)
        consolidated_data[ckey]['orders'].update(order_names.split(', '))
        consolidated_data[ckey]['lines'] += 1

        # Recursión por componentes de BOM
        if has_bom:
            for bom_line in bom.bom_line_ids:
                component = bom_line.product_id
                factor = bom_line.product_qty / (bom.product_qty or 1.0)
                new_cumulative = cumulative_factor * factor

                self._explode_product_bom(
                    explosion_vals, consolidated_data,
                    finished_product, component, warehouse,
                    demand_qty, new_cumulative, level + 1,
                    order_names, current_product, visited
                )

    def action_mark_done(self):
        self.ensure_one()
        self.state = 'done'

    def action_cancel(self):
        self.ensure_one()
        self.state = 'cancelled'

    def action_reset_draft(self):
        self.ensure_one()
        self.demand_line_ids.unlink()
        self.explosion_line_ids.unlink()
        self.consolidated_line_ids.unlink()
        self.state = 'draft'

    def action_refresh(self):
        """Regenera todo: demanda + explosión."""
        self.ensure_one()
        self.action_generate_demand()
        self.action_explode_bom()

    def action_view_demand(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Demanda de Producción'),
            'res_model': 'planning.demand.line',
            'view_mode': 'list,pivot,graph',
            'domain': [('snapshot_id', '=', self.id)],
            'context': {'default_snapshot_id': self.id},
        }

    def action_view_explosion(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Explosión de BOM'),
            'res_model': 'planning.bom.explosion.line',
            'view_mode': 'list,pivot,graph',
            'domain': [('snapshot_id', '=', self.id)],
            'context': {'default_snapshot_id': self.id},
        }

    def action_view_consolidated(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Demanda Consolidada'),
            'res_model': 'planning.bom.consolidated',
            'view_mode': 'list,pivot,graph',
            'domain': [('snapshot_id', '=', self.id)],
            'context': {'default_snapshot_id': self.id},
        }

    def action_view_critical(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Items Críticos'),
            'res_model': 'planning.bom.consolidated',
            'view_mode': 'list',
            'domain': [('snapshot_id', '=', self.id)],
            'context': {'default_snapshot_id': self.id},
        }