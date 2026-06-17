from odoo import models, fields


class DummyB(models.Model):
    _name = 'module.b.dummy'
    _description = 'Dummy Model B'

    name = fields.Char()
    active = fields.Boolean(default=True)