from odoo import models, fields


class DummyA(models.Model):
    _name = 'module.a.dummy'
    _description = 'Dummy Model A'

    name = fields.Char()
    description = fields.Text()
