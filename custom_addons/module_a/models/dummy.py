from odoo import models, fields


class DummyA(models.Model):
    _name = 'module.a.dummy'
    _description = 'Dummy Model A'

    name = fields.Char()
    description = fields.Text()
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    priority = fields.Selection([('0', 'Normal'), ('1', 'High')], default='0')
