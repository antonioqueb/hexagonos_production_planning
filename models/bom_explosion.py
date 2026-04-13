from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class BomExplosionLine(models.Model):
    _name = 'planning.bom.explosion.line'
    _description = 'Línea de Explosión de Lista de Materiales'
    _order = 'snapshot_id, finished_product_id, bom_level, product_id'

    snapshot_id = fields.Many2one('planning.snapshot', string='Snapshot', ondelete='cascade', index=True)

    # Producto terminado que origina la demanda
    finished_product_id = fields.Many2one('product.product', string='Producto Terminado', readonly=True, index=True)
    finished_product_code = fields.Char(string='Código PT', related='finished_product_id.default_code', store=True)

    # Producto componente (semi-elaborado o materia prima)
    product_id = fields.Many2one('product.product', string='Componente', readonly=True, index=True)
    product_code = fields.Char(string='Código Componente', related='product_id.default_code', store=True)
    product_type = fields.Selection([
        ('finished', 'Producto Terminado'),
        ('semi', 'Semi-elaborado'),
        ('raw', 'Materia Prima'),
    ], string='Tipo', readonly=True, index=True)

    bom_id = fields.Many2one('mrp.bom', string='Lista de Materiales', readonly=True)
    bom_level = fields.Integer(string='Nivel BOM', readonly=True, default=0)
    parent_product_id = fields.Many2one('product.product', string='Producto Padre', readonly=True)

    # Cantidades
    qty_per_unit = fields.Float(string='Cant. por Unidad PT', readonly=True, digits=(16, 4))
    demand_qty_finished = fields.Float(string='Demanda PT (pendiente)', readonly=True)
    qty_required = fields.Float(string='Cantidad Requerida', readonly=True,
                                 help='Cantidad total requerida = demanda PT pendiente * cant. por unidad')
    product_uom_id = fields.Many2one('uom.uom', string='UdM', readonly=True)

    # Almacén
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén', readonly=True, index=True)

    # Stock info
    qty_available = fields.Float(string='Stock Disponible', compute='_compute_stock', store=False)
    virtual_available = fields.Float(string='Stock Proyectado', compute='_compute_stock', store=False)
    qty_to_produce = fields.Float(string='Cantidad a Producir/Comprar', compute='_compute_stock', store=False)

    # Origen
    sale_order_ids = fields.Char(string='Órdenes de Venta', readonly=True)

    @api.depends('product_id', 'warehouse_id', 'qty_required')
    def _compute_stock(self):
        for line in self:
            if line.product_id and line.warehouse_id:
                product = line.product_id.with_context(warehouse=line.warehouse_id.id)
                line.qty_available = product.qty_available
                line.virtual_available = product.virtual_available
                line.qty_to_produce = max(0, line.qty_required - product.qty_available)
            else:
                line.qty_available = 0.0
                line.virtual_available = 0.0
                line.qty_to_produce = 0.0


class BomExplosionConsolidated(models.Model):
    _name = 'planning.bom.consolidated'
    _description = 'Demanda Consolidada por Componente'
    _order = 'product_type, product_id'

    snapshot_id = fields.Many2one('planning.snapshot', string='Snapshot', ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True, index=True)
    product_code = fields.Char(string='Código', related='product_id.default_code', store=True)
    product_type = fields.Selection([
        ('finished', 'Producto Terminado'),
        ('semi', 'Semi-elaborado'),
        ('raw', 'Materia Prima'),
    ], string='Tipo', readonly=True, index=True)
    product_uom_id = fields.Many2one('uom.uom', string='UdM', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén', readonly=True, index=True)

    total_required = fields.Float(string='Total Requerido', readonly=True)
    qty_available = fields.Float(string='Stock Disponible', compute='_compute_stock', store=False)
    virtual_available = fields.Float(string='Stock Proyectado', compute='_compute_stock', store=False)
    qty_gap = fields.Float(string='Brecha', compute='_compute_stock', store=False,
                            help='Cantidad que falta producir o comprar')
    coverage_pct = fields.Float(string='% Cobertura', compute='_compute_stock', store=False)

    # Detalle de origen
    finished_product_names = fields.Text(string='Productos Terminados que lo requieren', readonly=True)
    sale_order_names = fields.Text(string='Órdenes de Venta relacionadas', readonly=True)
    demand_line_count = fields.Integer(string='# Líneas Demanda', readonly=True)

    @api.depends('product_id', 'warehouse_id', 'total_required')
    def _compute_stock(self):
        for line in self:
            if line.product_id and line.warehouse_id:
                product = line.product_id.with_context(warehouse=line.warehouse_id.id)
                line.qty_available = product.qty_available
                line.virtual_available = product.virtual_available
                line.qty_gap = max(0, line.total_required - product.qty_available)
                line.coverage_pct = (product.qty_available / line.total_required * 100) if line.total_required else 100.0
            else:
                line.qty_available = 0.0
                line.virtual_available = 0.0
                line.qty_gap = line.total_required
                line.coverage_pct = 0.0
