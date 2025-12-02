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

        # 🔹 Antes de tocar nada, ver a qué plan/cola pertenece esta WO
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

            # 4) Si todas las WOs de la MO quedaron 'done', cerrar la MO (esto asienta stock del terminado)
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
                    # Nota informativa en el chatter
                    try:
                        mo.message_post(body=_("MO %s cerrada automáticamente desde terminal de taller.") % mo.name)
                    except Exception:
                        pass

            # 5) SCRAP (después de intentar cerrar la MO)
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

                    # Si la MO quedó cerrada ahora, ya hay stock en destino → validar scrap ya.
                    # Si no, lo dejamos en borrador para que no falle por falta de stock.
                    if mo_closed_now:
                        try:
                            sc.action_validate()
                        except Exception:
                            scrap_msg = _(" (El desecho quedó en borrador por no poder validarse ahora.)")
                    else:
                        scrap_msg = _(" (El desecho quedó en borrador y se podrá validar al cerrar la MO.)")
                else:
                    scrap_msg = _(" (No se encontró ubicación/campo de desecho; se omitió el scrap.)")

            # 🔹 6) Imprimir la siguiente OT de la cola, copiando la lógica del botón 🖨
            next_report_url = False
            if plan_id:
                try:
                    plan = env['work.queue.plan'].sudo().browse(plan_id)
                    if plan and plan.exists():
                        # La cola ya no tiene la WO que acabamos de terminar porque el inherit
                        # mrp_workorder_queue_clean borra ese item al pasar a 'done'.
                        # Ahora la "siguiente" es la que tenga menor sequence.
                        ordered = plan.line_ids.sorted(lambda x: x.sequence)
                        if ordered:
                            next_item = ordered[0]
                            next_wo = next_item.workorder_id

                            if next_wo and next_wo.exists():
                                # **************
                                # COPIA DE LÓGICA DE action_print_wo_80mm,
                                # pero sin chequear "solo la primera de la cola"
                                # **************
                                # 1) Reanudar limpio por si estaba pausada
                                try:
                                    from odoo.exceptions import UserError
                                except ImportError:
                                    UserError = Exception

                                try:
                                    # importamos la función force_resume_wo del mismo lugar
                                    from odoo.addons.mrp_work_queue.models.queue_item import force_resume_wo
                                except Exception:
                                    force_resume_wo = None

                                if force_resume_wo:
                                    try:
                                        force_resume_wo(next_wo)
                                    except Exception:
                                        _logger.exception("Error al intentar reanudar WO %s antes de imprimir.", next_wo.name)

                                # 2) Asignar responsable si el plan tiene empleado y la MO no tiene usuario
                                if plan.employee_id and not next_wo.production_id.user_id and plan.employee_id.user_id:
                                    next_wo.production_id.write({'user_id': plan.employee_id.user_id.id})

                                # 3) Obtener la acción de reporte exactamente igual que en el botón
                                report_action = env.ref(
                                    'mrp_work_queue.action_report_mrp_workorder_80mm',
                                    raise_if_not_found=False
                                ) or env['ir.actions.report']._get_report_from_name(
                                    'mrp_work_queue.report_workorder_80mm'
                                )

                                if report_action:
                                    # En lugar de retornar la acción al cliente (como en el backend),
                                    # armamos directamente la URL del PDF:
                                    # /report/pdf/<report_name>/<res_id>
                                    # el "name" técnico del reporte es el mismo que se usa en el XML.
                                    report_name = report_action.report_name or 'mrp_work_queue.report_workorder_80mm'
                                    res_id = next_wo.id
                                    next_report_url = "/report/pdf/%s/%s" % (report_name, res_id)
                                else:
                                    _logger.warning("No se encontró la acción de reporte 80mm.")
                except Exception as e:
                    _logger.exception("Error al intentar imprimir siguiente OT de cola: %s", e)
                    next_report_url = False

            # 7) Mensaje final
            finished_dt = getattr(wo, 'date_finished', None) or getattr(wo, 'date_end', None)
            msg = _("Orden finalizada. OK: %(ok).2f, Rechazo: %(rej).2f. Cierre: %(dt)s%(extra)s") % {
                'ok': ok_qty,
                'rej': rej_qty,
                'dt': _fmt_dt(finished_dt),
                'extra': scrap_msg,
            }
            return request.render('mrp_work_queue.wo_finish_result', {
                'ok': True,
                'message': msg,
                'next_report_url': next_report_url,
            })

        except Exception as e:
            _logger.exception("Error finalizando WO %s", wo.name)
            return request.render('mrp_work_queue.wo_finish_result', {
                'ok': False,
                'message': _("Error al finalizar: %s") % (str(e),)
            })