from odoo import models, fields, api, _


class ExplodeBomWizard(models.TransientModel):
    _name = 'planning.explode.bom.wizard'
    _description = 'Asistente para Explotar BOM'

    snapshot_id = fields.Many2one('planning.snapshot', string='Snapshot', required=True)
    max_levels = fields.Integer(string='Máximo niveles de explosión', default=10)

    def action_explode(self):
        self.ensure_one()
        return self.snapshot_id.action_explode_bom()
