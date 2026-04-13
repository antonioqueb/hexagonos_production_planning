from odoo import models, fields, api, _


class GenerateDemandWizard(models.TransientModel):
    _name = 'planning.generate.demand.wizard'
    _description = 'Asistente para Generar Demanda'

    snapshot_id = fields.Many2one('planning.snapshot', string='Snapshot', required=True)
    date_from = fields.Date(string='Fecha Desde')
    date_to = fields.Date(string='Fecha Hasta')
    warehouse_ids = fields.Many2many('stock.warehouse', string='Almacenes')
    partner_ids = fields.Many2many('res.partner', string='Clientes')
    include_done = fields.Boolean(string='Incluir órdenes bloqueadas', default=False)

    def action_generate(self):
        self.ensure_one()
        snapshot = self.snapshot_id
        if self.date_from:
            snapshot.date_from = self.date_from
        if self.date_to:
            snapshot.date_to = self.date_to
        if self.warehouse_ids:
            snapshot.warehouse_ids = self.warehouse_ids
        if self.partner_ids:
            snapshot.partner_ids = self.partner_ids
        return snapshot.action_generate_demand()
