# -*- coding: utf-8 -*-
import logging
from odoo import http, _, fields as odoo_fields
from odoo.http import request
from werkzeug.exceptions import NotFound

_logger = logging.getLogger(__name__)


def _to_float(s):
    if s is None:
        return 0.0
    s = str(s).strip().replace(',', '.')
    try:
        return float(s)
    except Exception:
        return 0.0


def _fmt_dt(dt):
    """Devuelve dt con TZ del usuario en 'YYYY-MM-DD HH:MM:SS'."""
    if not dt:
        return "-"
    try:
        dt_loc = odoo_fields.Datetime.context_timestamp(request.env.user, dt)
        return dt_loc.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(dt)


class WoScanController(http.Controller):

    @http.route('/wo/<int:wo_id>', type='http', auth='user', methods=['GET'], csrf=False)
    def wo_form(self, wo_id, **kw):
        wo = request.env['mrp.workorder'].sudo().browse(wo_id)
        if not wo.exists():
            raise NotFound()

        # 1) Si la OT ya está terminada, mostramos info y NO dejamos cargar nada
        if wo.state == 'done':
            produced = getattr(wo, 'qty_produced', 0.0)
            # campos de fecha de fin varían por versión
            finished_dt = getattr(wo, 'date_finished', None) or getattr(wo, 'date_end', None)
            msg = _(
                "La orden %(name)s ya fue finalizada.\n"
                "Producto: %(prod)s\n"
                "Cantidad producida: %(qty).2f %(uom)s\n"
                "Fecha/hora cierre: %(dt)s"
            ) % {
                'name': wo.name,
                'prod': wo.product_id.display_name,
                'qty': produced or 0.0,
                'uom': wo.product_uom_id.name if wo.product_uom_id else '',
                'dt' : _fmt_dt(finished_dt),
            }
            return request.render('mrp_work_queue.wo_finish_result', {
                'ok': False,
                'message': msg,
            })

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

        # Si ya está terminada, bloqueamos y mostramos info
        if wo.state == 'done':
            produced = getattr(wo, 'qty_produced', 0.0)
            finished_dt = getattr(wo, 'date_finished', None) or getattr(wo, 'date_end', None)
            msg = _(
                "La orden %(name)s ya fue finalizada.\n"
                "Producto: %(prod)s\n"
                "Cantidad producida: %(qty).2f %(uom)s\n"
                "Fecha/hora cierre: %(dt)s"
            ) % {
                'name': wo.name,
                'prod': wo.product_id.display_name,
                'qty': produced or 0.0,
                'uom': wo.product_uom_id.name if wo.product_uom_id else '',
                'dt' : _fmt_dt(finished_dt),
            }
            return request.render('mrp_work_queue.wo_finish_result', {
                'ok': False,
                'message': msg,
            })

        ok_qty  = _to_float(post.get('ok_qty'))
        rej_qty = _to_float(post.get('rej_qty'))
        if ok_qty < 0: ok_qty = 0.0
        if rej_qty < 0: rej_qty = 0.0
        total_qty = ok_qty + rej_qty

        try:
            # 1) Asegurar la OT en progreso
            if wo.state not in ('progress', 'done'):
                if hasattr(wo, 'button_start'):
                    wo.button_start()
                elif hasattr(wo, 'action_start'):
                    wo.action_start()

            # 2) Registrar producción de TODO lo procesado (OK + Rechazo)
            #    -> los componentes quedan consumidos por el total
            if total_qty > 0:
                if hasattr(wo, 'record_production'):
                    wo.qty_producing = total_qty
                    wo.record_production()
                elif hasattr(wo, 'button_finish'):
                    wo.qty_producing = total_qty
                    wo.button_finish()
                else:
                    # Fallback muy básico por versión antigua
                    prod = wo.production_id
                    for mv in prod.move_finished_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                        mv.quantity_done += total_qty
                    if hasattr(prod, 'button_mark_done'):
                        prod.button_mark_done()

            # 3) SCRAP de rechazadas (si aplica) desde el depósito de terminados
            if rej_qty > 0:
                Scrap = env['stock.scrap'].sudo()
                dest_field = 'scrap_location_id' if 'scrap_location_id' in Scrap._fields else (
                            'location_dest_id' if 'location_dest_id' in Scrap._fields else None)

                scrap_loc = env.ref('stock.stock_location_scrapped', raise_if_not_found=False) \
                            or env.ref('stock.location_scrapped', raise_if_not_found=False)
                if not scrap_loc:
                    scrap_loc = env['stock.location'].sudo().search([('scrap_location', '=', True)], limit=1)

                if not dest_field or not scrap_loc:
                    _logger.warning("No se encontró campo destino o ubicación de scrap; se omite el scrap.")
                else:
                    # desde el depósito de productos terminados de la MO
                    src_loc = wo.production_id.location_dest_id or env.ref('stock.stock_location_stock')
                    vals = {
                        'product_id': wo.product_id.id,
                        'product_uom_id': wo.product_uom_id.id if wo.product_uom_id else wo.product_id.uom_id.id,
                        'scrap_qty': rej_qty,
                        'company_id': wo.company_id.id,
                        'origin': 'WO %s' % wo.name,
                        'location_id': src_loc.id,
                        dest_field: scrap_loc.id,
                        'production_id': wo.production_id.id,
                    }
                    scrap = Scrap.create(vals)
                    scrap.action_validate()

            # 4) Cerrar la OT si sigue abierta
            if wo.state != 'done':
                if hasattr(wo, 'button_finish'):
                    wo.button_finish()
                elif hasattr(wo, 'action_done'):
                    wo.action_done()

            # 5) Si todas las OTs de la MO quedaron 'done', cerrar la MO
            mo = wo.production_id
            if mo and mo.state != 'done':
                all_done = all(w.state == 'done' for w in mo.workorder_ids)
                if all_done:
                    if hasattr(mo, 'button_mark_done'):
                        mo.button_mark_done()
                    elif hasattr(mo, 'action_done'):
                        mo.action_done()

            # Info para el mensaje final
            finished_dt = getattr(wo, 'date_finished', None) or getattr(wo, 'date_end', None)
            msg = _("Orden finalizada. OK: %(ok).2f, Rechazo: %(rej).2f. Cierre: %(dt)s") % {
                'ok': ok_qty, 'rej': rej_qty, 'dt': _fmt_dt(finished_dt),
            }
            return request.render('mrp_work_queue.wo_finish_result', {'ok': True, 'message': msg})

        except Exception as e:
            _logger.exception("Error finalizando WO %s", wo.name)
            return request.render('mrp_work_queue.wo_finish_result', {
                'ok': False,
                'message': _("Error al finalizar: %s") % (str(e),)
            })