# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from werkzeug.exceptions import NotFound
import logging

_logger = logging.getLogger(__name__)

def _to_float(s):
    if s is None:
        return 0.0
    s = str(s).strip().replace(',', '.')
    try:
        return float(s)
    except Exception:
        return 0.0

class WoScanController(http.Controller):

    @http.route('/wo/<int:wo_id>', type='http', auth='user', methods=['GET'], csrf=False)
    def wo_form(self, wo_id, **kw):
        wo = request.env['mrp.workorder'].sudo().browse(wo_id)
        if not wo.exists():
            raise NotFound()
        values = {
            'wo': wo,
            'product': wo.product_id,
            'title': _("Orden de trabajo: %s") % (wo.name,),
            'ok_default': "",
            'rej_default': "0",
        }
        return request.render('mrp_work_queue.wo_finish_form', values)

    @http.route('/wo/<int:wo_id>/finish', type='http', auth='user', methods=['POST'], csrf=False)
    def wo_finish(self, wo_id, **post):
        env = request.env
        wo = env['mrp.workorder'].sudo().browse(wo_id)
        if not wo.exists():
            return request.render('mrp_work_queue.wo_finish_result', {
                'ok': False,
                'message': _("La orden no existe.")
            })

        ok_qty  = _to_float(post.get('ok_qty'))
        rej_qty = _to_float(post.get('rej_qty'))
        if ok_qty < 0: ok_qty = 0.0
        if rej_qty < 0: rej_qty = 0.0
        total_qty = ok_qty + rej_qty

        try:
            # 1) Asegurar estado en progreso
            if wo.state not in ('progress', 'done'):
                if hasattr(wo, 'button_start'):
                    wo.button_start()
                elif hasattr(wo, 'action_start'):
                    wo.action_start()

            # 2) Producir TODO lo procesado (OK + rechazadas)
            if total_qty > 0:
                if hasattr(wo, 'record_production'):
                    wo.qty_producing = total_qty
                    wo.record_production()
                elif hasattr(wo, 'button_finish'):
                    wo.qty_producing = total_qty
                    wo.button_finish()
                else:
                    prod = wo.production_id
                    for mv in prod.move_finished_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                        mv.quantity_done += total_qty
                    if hasattr(prod, 'button_mark_done'):
                        prod.button_mark_done()

            # 3) Mover las rechazadas a SCRAP (del producto terminado)
            if rej_qty > 0:
                # localizar depósito de scrap de forma segura
                scrap_loc = env.ref('stock.stock_location_scrapped', raise_if_not_found=False) \
                            or env.ref('stock.location_scrapped', raise_if_not_found=False)
                if not scrap_loc:
                    scrap_loc = env['stock.location'].search([('scrap_location', '=', True)], limit=1)

                # desde dónde sale el producto terminado
                src_loc = wo.production_id.location_dest_id or env.ref('stock.stock_location_stock')

                scrap_vals = {
                    'product_id': wo.product_id.id,
                    'product_uom_id': wo.product_uom_id.id,
                    'scrap_qty': rej_qty,
                    'company_id': wo.company_id.id,
                    'origin': 'WO %s' % wo.name,
                    'location_id': src_loc.id,
                    'location_dest_id': scrap_loc.id if scrap_loc else src_loc.id,
                    'production_id': wo.production_id.id,
                }
                scrap = env['stock.scrap'].create(scrap_vals)
                scrap.action_validate()

            # 4) Cerrar la OT si sigue abierta
            if wo.state != 'done':
                if hasattr(wo, 'button_finish'):
                    wo.button_finish()
                elif hasattr(wo, 'action_done'):
                    wo.action_done()

            # Mensaje formateado correctamente (mapping)
            msg = _("Orden finalizada. OK: %(ok).2f, Rechazo: %(rej).2f") % {'ok': ok_qty, 'rej': rej_qty}
            return request.render('mrp_work_queue.wo_finish_result', {'ok': True, 'message': msg})

        except Exception as e:
            _logger.exception("Error finalizando WO %s", wo.name)
            return request.render('mrp_work_queue.wo_finish_result', {
                'ok': False,
                'message': _("Error al finalizar: %s") % (str(e),)
            })