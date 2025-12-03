# -*- coding: utf-8 -*-
import logging
import json

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
        """Formulario simple para cerrar una OT desde el terminal."""
        wo = request.env['mrp.workorder'].sudo().browse(wo_id)
        if not wo.exists():
            raise NotFound()

        # Si la OT ya está terminada, mostramos info y NO dejamos cargar nada
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
                'dt': _fmt_dt(finished_dt),
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
        """Cierra la OT y dispara la descarga de la siguiente OT en la cola (PDF 80mm)."""
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
                'dt': _fmt_dt(finished_dt),
            }
            return request.render('mrp_work_queue.wo_finish_result', {
                'ok': False,
                'message': msg,
            })

        # 🔹 Averiguar a qué plan/cola pertenece esta WO (antes de tocar estados)
        plan_id = False
        try:
            queue_item = env['work.queue.item'].sudo().search(
                [('workorder_id', '=', wo.id)],
                limit=1
            )
            if queue_item and queue_item.plan_id:
                plan_id = queue_item.plan_id.id
        except Exception as e:
            _logger.exception("Error obteniendo plan de cola para WO %s: %s", wo.name, e)
            plan_id = False

        ok_qty = _to_float(post.get('ok_qty'))
        rej_qty = _to_float(post.get('rej_qty'))
        if ok_qty < 0:
            ok_qty = 0.0
        if rej_qty < 0:
            rej_qty = 0.0
        total_qty = ok_qty + rej_qty

        try:
            # 1) Asegurar la OT en progreso
            if wo.state not in ('progress', 'done'):
                if hasattr(wo, 'button_start'):
                    wo.button_start()
                elif hasattr(wo, 'action_start'):
                    wo.action_start()

            # 2) Registrar producción de TODO lo procesado (OK + Rechazo)
            if total_qty > 0:
                if hasattr(wo, 'record_production'):
                    wo.qty_producing = total_qty
                    wo.record_production()
                elif hasattr(wo, 'button_finish'):
                    wo.qty_producing = total_qty
                    wo.button_finish()

            # 3) Cerrar la WO si sigue abierta
            if wo.state != 'done':
                if hasattr(wo, 'button_finish'):
                    wo.button_finish()
                elif hasattr(wo, 'action_done'):
                    wo.action_done()

            # 4) Si todas las WOs de la MO quedaron 'done', cerrar la MO
            mo = wo.production_id
            mo_closed_now = False
            if mo and mo.state != 'done':
                all_done = all(w.state == 'done' for w in mo.workorder_ids)
                if all_done:
                    if hasattr(mo, 'button_mark_done'):
                        mo.button_mark_done()
                    elif hasattr(mo, 'action_done'):
                        mo.action_done()
                    mo_closed_now = (mo.state == 'done')
                    try:
                        mo.message_post(body=_("MO %s cerrada automáticamente desde terminal de taller.") % mo.name)
                    except Exception:
                        pass

            # 5) SCRAP
            scrap_msg = ""
            if rej_qty > 0:
                Scrap = env['stock.scrap'].sudo()
                dest_field = 'scrap_location_id' if 'scrap_location_id' in Scrap._fields else (
                    'location_dest_id' if 'location_dest_id' in Scrap._fields else None
                )

                scrap_loc = env.ref('stock.stock_location_scrapped', raise_if_not_found=False) \
                            or env.ref('stock.location_scrapped', raise_if_not_found=False)
                if not scrap_loc:
                    scrap_loc = env['stock.location'].sudo().search([('scrap_location', '=', True)], limit=1)

                if dest_field and scrap_loc:
                    src_loc = mo.location_dest_id or env.ref('stock.stock_location_stock').sudo()
                    vals = {
                        'product_id': wo.product_id.id,
                        'product_uom_id': (wo.product_uom_id and wo.product_uom_id.id) or wo.product_id.uom_id.id,
                        'scrap_qty': rej_qty,
                        'company_id': wo.company_id.id,
                        'origin': 'MO %s / WO %s' % (mo.name, wo.name),
                        'location_id': src_loc.id,
                    }
                    if 'production_id' in Scrap._fields:
                        vals['production_id'] = mo.id
                    vals[dest_field] = scrap_loc.id

                    sc = Scrap.create(vals)

                    if mo_closed_now:
                        try:
                            sc.action_validate()
                        except Exception:
                            scrap_msg = _(" (El desecho quedó en borrador por no poder validarse ahora.)")
                    else:
                        scrap_msg = _(" (El desecho quedó en borrador y se podrá validar al cerrar la MO.)")
                else:
                    scrap_msg = _(" (No se encontró ubicación/campo de desecho; se omitió el scrap.)")

            # 🔹 6) Buscar la siguiente OT en la cola (nueva primera)
            next_wo = False
            if plan_id:
                try:
                    plan = env['work.queue.plan'].sudo().browse(plan_id)
                    if plan and plan.exists():
                        ordered = plan.line_ids.sorted(lambda x: x.sequence)
                        if ordered:
                            next_item = ordered[0]
                            next_wo = next_item.workorder_id
                            _logger.info(
                                "Siguiente OT en cola para plan %s: %s (%s)",
                                plan.display_name,
                                next_wo.id if next_wo else None,
                                next_wo.name if next_wo else None,
                            )
                        else:
                            _logger.info("Plan %s no tiene más líneas en la cola.", plan.display_name)
                    else:
                        _logger.info("Plan %s no existe o no tiene líneas.", plan_id)
                except Exception as e:
                    _logger.exception("Error obteniendo siguiente OT de la cola: %s", e)
                    next_wo = False

            # 7) Mensaje final (usado siempre)
            finished_dt = getattr(wo, 'date_finished', None) or getattr(wo, 'date_end', None)
            msg = _("Orden finalizada. OK: %(ok).2f, Rechazo: %(rej).2f. Cierre: %(dt)s%(extra)s") % {
                'ok': ok_qty,
                'rej': rej_qty,
                'dt': _fmt_dt(finished_dt),
                'extra': scrap_msg,
            }

            # Si NO hay siguiente OT en la cola, mostramos la pantalla de resultado como siempre
            if not next_wo or not next_wo.exists():
                _logger.info("WO %s finalizada. No hay siguiente OT en cola para imprimir.", wo.name)
                return request.render('mrp_work_queue.wo_finish_result', {
                    'ok': True,
                    'message': msg,
                })

            # 🔹 8) Si HAY siguiente OT, armamos el mismo payload que usa el botón hacia /report/download
            report_name = "mrp_work_queue.report_workorder_80mm"
            pdf_url = "/report/pdf/%s/%s" % (report_name, next_wo.id)

            # EXACTAMENTE lo que viste en DevTools:
            # data = ["/report/pdf/mrp_work_queue.report_workorder_80mm/131","qweb-pdf"]
            data_payload = json.dumps([pdf_url, "qweb-pdf"])

            _logger.info(
                "Preparando auto-descarga de siguiente OT %s (%s) con data=%s",
                next_wo.name,
                next_wo.id,
                data_payload,
            )

            return request.render('mrp_work_queue.wo_finish_download', {
                'ok': True,
                'message': msg,
                'data_payload': data_payload,
            })

        except Exception as e:
            _logger.exception("Error finalizando WO %s", wo.name)
            return request.render('mrp_work_queue.wo_finish_result', {
                'ok': False,
                'message': _("Error al finalizar: %s") % (str(e),)
            })
