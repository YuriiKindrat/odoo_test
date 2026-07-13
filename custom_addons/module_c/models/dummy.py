from odoo import models, fields


class DummyC(models.Model):
    _name = 'module.c.dummy'
    _description = 'Dummy Model C'

    name = fields.Char()
    active = fields.Boolean(default=True)
    description = fields.Text()


