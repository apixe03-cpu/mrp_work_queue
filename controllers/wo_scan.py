# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class WOScan(http.Controller):

    @http.route('/wo/<int:wo_id>', type='http', auth='user', website=True)
    def wo_form(self, wo_id, **kw):
        wo = request.env['mrp.workorder'].sudo().browse(wo_id)
        if not wo.exists():
            return request.not_found()
        return request.render('mrp_work_queue.wo_scan_form', {
            'wo': wo,
        })

    @http.route('/wo/<int:wo_id>/submit', type='http', auth='user', methods=['POST'], csrf=False)
    def wo_submit(self, wo_id, **post):
        wo = request.env['mrp.workorder'].sudo().browse(wo_id)
        if not wo.exists():
            return request.not_found()

        def _f(k):
            try:
                return float(post.get(k) or 0)
            except Exception:
                return 0.0

        qty_good = _f('qty_good')
        qty_scrap = _f('qty_scrap')

        # Método robusto en el modelo (abajo) que registra scrap y finaliza
        wo.sudo().with_context(qty_good=qty_good, qty_scrap=qty_scrap).action_finish_from_qr()

        # Redirigimos al form estándar por si quieren mirar el resultado
        return request.redirect('/web#id=%s&model=mrp.workorder&view_type=form' % wo_id)