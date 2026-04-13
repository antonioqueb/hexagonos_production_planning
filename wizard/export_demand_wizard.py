import base64
import io
from odoo import models, fields, api, _
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class ExportDemandWizard(models.TransientModel):
    _name = 'planning.export.demand.wizard'
    _description = 'Exportar Demanda a Excel'

    snapshot_id = fields.Many2one('planning.snapshot', string='Snapshot', required=True)
    export_type = fields.Selection([
        ('demand', 'Demanda de Ventas'),
        ('explosion', 'Explosión de BOM'),
        ('consolidated', 'Demanda Consolidada'),
        ('full', 'Reporte Completo'),
    ], string='Tipo de Exportación', default='full', required=True)
    file_data = fields.Binary(string='Archivo', readonly=True)
    file_name = fields.Char(string='Nombre de Archivo', readonly=True)

    def action_export(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(_('Se requiere la librería xlsxwriter.'))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # Formatos
        header_fmt = workbook.add_format({
            'bold': True, 'bg_color': '#2E86C1', 'font_color': 'white',
            'border': 1, 'text_wrap': True, 'valign': 'vcenter',
        })
        number_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
        text_fmt = workbook.add_format({'border': 1, 'text_wrap': True})
        date_fmt = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm', 'border': 1})
        pct_fmt = workbook.add_format({'num_format': '0.0%', 'border': 1})
        critical_fmt = workbook.add_format({
            'bg_color': '#FADBD8', 'border': 1, 'num_format': '#,##0.00'
        })

        snapshot = self.snapshot_id

        if self.export_type in ('demand', 'full'):
            self._write_demand_sheet(workbook, snapshot, header_fmt, text_fmt, number_fmt, date_fmt)

        if self.export_type in ('explosion', 'full'):
            self._write_explosion_sheet(workbook, snapshot, header_fmt, text_fmt, number_fmt)

        if self.export_type in ('consolidated', 'full'):
            self._write_consolidated_sheet(workbook, snapshot, header_fmt, text_fmt, number_fmt, pct_fmt, critical_fmt)

        workbook.close()
        output.seek(0)

        self.file_data = base64.b64encode(output.read())
        self.file_name = f"Planificacion_{snapshot.name}_{fields.Date.today()}.xlsx"

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _write_demand_sheet(self, workbook, snapshot, header_fmt, text_fmt, number_fmt, date_fmt):
        ws = workbook.add_worksheet('Demanda de Ventas')
        headers = [
            'Referencia de Orden', 'Almacén', 'Cliente', 'Descripción',
            'Cantidad', 'Entregado', 'Pendiente', 'Fecha Entrega',
            'Fecha Orden', 'Nro. Cliente', 'Código Único', 'Estado',
            'Stock Disponible', 'Stock Proyectado', 'Brecha',
        ]
        for col, h in enumerate(headers):
            ws.write(0, col, h, header_fmt)
            ws.set_column(col, col, 15)

        for row, dl in enumerate(snapshot.demand_line_ids, 1):
            ws.write(row, 0, dl.sale_order_name or '', text_fmt)
            ws.write(row, 1, dl.warehouse_id.name or '', text_fmt)
            ws.write(row, 2, dl.partner_id.name or '', text_fmt)
            ws.write(row, 3, dl.product_description or '', text_fmt)
            ws.write(row, 4, dl.product_uom_qty, number_fmt)
            ws.write(row, 5, dl.qty_delivered, number_fmt)
            ws.write(row, 6, dl.qty_pending, number_fmt)
            ws.write(row, 7, str(dl.commitment_date or ''), text_fmt)
            ws.write(row, 8, str(dl.order_date or ''), text_fmt)
            ws.write(row, 9, dl.partner_number or '', text_fmt)
            ws.write(row, 10, dl.product_default_code or '', text_fmt)
            ws.write(row, 11, dl.state or '', text_fmt)
            ws.write(row, 12, dl.qty_available, number_fmt)
            ws.write(row, 13, dl.virtual_available, number_fmt)
            ws.write(row, 14, dl.stock_gap, number_fmt)

    def _write_explosion_sheet(self, workbook, snapshot, header_fmt, text_fmt, number_fmt):
        ws = workbook.add_worksheet('Explosión BOM')
        headers = [
            'Producto Terminado', 'Código PT', 'Componente', 'Código Comp.',
            'Tipo', 'Nivel BOM', 'Cant/Unidad PT', 'Demanda PT',
            'Cantidad Requerida', 'UdM', 'Almacén',
            'Stock Disp.', 'Proyectado', 'A Producir/Comprar', 'Órdenes',
        ]
        for col, h in enumerate(headers):
            ws.write(0, col, h, header_fmt)
            ws.set_column(col, col, 15)

        type_labels = {'finished': 'PT', 'semi': 'Semi-elaborado', 'raw': 'Materia Prima'}
        for row, el in enumerate(snapshot.explosion_line_ids, 1):
            ws.write(row, 0, el.finished_product_id.display_name or '', text_fmt)
            ws.write(row, 1, el.finished_product_code or '', text_fmt)
            ws.write(row, 2, el.product_id.display_name or '', text_fmt)
            ws.write(row, 3, el.product_code or '', text_fmt)
            ws.write(row, 4, type_labels.get(el.product_type, ''), text_fmt)
            ws.write(row, 5, el.bom_level, number_fmt)
            ws.write(row, 6, el.qty_per_unit, number_fmt)
            ws.write(row, 7, el.demand_qty_finished, number_fmt)
            ws.write(row, 8, el.qty_required, number_fmt)
            ws.write(row, 9, el.product_uom_id.name or '', text_fmt)
            ws.write(row, 10, el.warehouse_id.name or '', text_fmt)
            ws.write(row, 11, el.qty_available, number_fmt)
            ws.write(row, 12, el.virtual_available, number_fmt)
            ws.write(row, 13, el.qty_to_produce, number_fmt)
            ws.write(row, 14, el.sale_order_ids or '', text_fmt)

    def _write_consolidated_sheet(self, workbook, snapshot, header_fmt, text_fmt, number_fmt, pct_fmt, critical_fmt):
        ws = workbook.add_worksheet('Consolidado')
        headers = [
            'Producto', 'Código', 'Tipo', 'UdM', 'Almacén',
            'Total Requerido', 'Stock Disp.', 'Proyectado',
            'Brecha', '% Cobertura', 'PTs que lo requieren', 'Órdenes Venta',
        ]
        for col, h in enumerate(headers):
            ws.write(0, col, h, header_fmt)
            ws.set_column(col, col, 18)

        type_labels = {'finished': 'PT', 'semi': 'Semi-elaborado', 'raw': 'Materia Prima'}
        for row, cl in enumerate(snapshot.consolidated_line_ids, 1):
            fmt = critical_fmt if cl.coverage_pct < 50 else number_fmt
            ws.write(row, 0, cl.product_id.display_name or '', text_fmt)
            ws.write(row, 1, cl.product_code or '', text_fmt)
            ws.write(row, 2, type_labels.get(cl.product_type, ''), text_fmt)
            ws.write(row, 3, cl.product_uom_id.name or '', text_fmt)
            ws.write(row, 4, cl.warehouse_id.name or '', text_fmt)
            ws.write(row, 5, cl.total_required, fmt)
            ws.write(row, 6, cl.qty_available, fmt)
            ws.write(row, 7, cl.virtual_available, fmt)
            ws.write(row, 8, cl.qty_gap, fmt)
            ws.write(row, 9, cl.coverage_pct / 100.0, pct_fmt)
            ws.write(row, 10, cl.finished_product_names or '', text_fmt)
            ws.write(row, 11, cl.sale_order_names or '', text_fmt)
