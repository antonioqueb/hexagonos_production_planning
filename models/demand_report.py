from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DemandReportLine(models.Model):
    _name = 'planning.demand.line'
    _description = 'Línea de Demanda de Producción'
    _order = 'commitment_date asc, sale_order_id asc'
    _rec_name = 'display_name'

    snapshot_id = fields.Many2one('planning.snapshot', string='Snapshot', ondelete='cascade', index=True)
    sale_order_id = fields.Many2one('sale.order', string='Orden de Venta', readonly=True, index=True)
    sale_order_name = fields.Char(string='Referencia de Orden', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True, index=True)
    partner_number = fields.Char(string='Número Cliente', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén', readonly=True, index=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True, index=True)
    product_tmpl_id = fields.Many2one('product.template', string='Plantilla Producto',
                                       related='product_id.product_tmpl_id', store=True, readonly=True)
    product_description = fields.Text(string='Descripción', readonly=True)
    product_default_code = fields.Char(string='Código Único', related='product_id.default_code', store=True, readonly=True)
    product_uom_qty = fields.Float(string='Cantidad Demandada', readonly=True)
    qty_delivered = fields.Float(string='Cantidad Entregada', readonly=True)
    qty_pending = fields.Float(string='Cantidad Pendiente', compute='_compute_qty_pending', store=True)
    product_uom_id = fields.Many2one('uom.uom', string='UdM', readonly=True)
    commitment_date = fields.Datetime(string='Fecha de Entrega', readonly=True)
    order_date = fields.Datetime(string='Fecha de Orden', readonly=True)
    state = fields.Selection([
        ('sale', 'Confirmada'),
        ('done', 'Bloqueada'),
    ], string='Estado', readonly=True)
    sale_line_id = fields.Many2one('sale.order.line', string='Línea de Venta', readonly=True)
    activity_note = fields.Char(string='Actividades', readonly=True)

    # Stock fields
    qty_available = fields.Float(string='Disponible en Stock', compute='_compute_stock_info', store=False)
    virtual_available = fields.Float(string='Proyectado', compute='_compute_stock_info', store=False)
    stock_gap = fields.Float(string='Brecha (Pendiente - Disponible)', compute='_compute_stock_info', store=False)

    display_name = fields.Char(compute='_compute_display_name', store=False)

    @api.depends('sale_order_name', 'product_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.sale_order_name or ''} - {rec.product_id.display_name or ''}"

    @api.depends('product_uom_qty', 'qty_delivered')
    def _compute_qty_pending(self):
        for line in self:
            line.qty_pending = line.product_uom_qty - line.qty_delivered

    @api.depends('product_id', 'warehouse_id')
    def _compute_stock_info(self):
        for line in self:
            if line.product_id and line.warehouse_id:
                product = line.product_id.with_context(warehouse=line.warehouse_id.id)
                line.qty_available = product.qty_available
                line.virtual_available = product.virtual_available
                line.stock_gap = line.qty_pending - product.qty_available
            else:
                line.qty_available = 0.0
                line.virtual_available = 0.0
                line.stock_gap = 0.0
