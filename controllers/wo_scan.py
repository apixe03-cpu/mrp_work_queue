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
    """Formatea con TZ del usuario."""
    if not dt:
        return "-"
    try:
        dt_loc = odoo_fields.Datetime.context_timestamp(request.env.user, dt)
        return dt_loc.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(dt)


class WoScanController(http.Controller):
    # ---------- helpers de lectura ----------
    def _wo_close_dt(self, wo):
        # último registro de tiempo, si existe; si no, la MO
        if getattr(wo, 'time_ids', False) and wo.time_ids:
            last = wo.time_ids.sorted(lambda t: t.date_end or t.date_start)[-1]
            return last.date_end or last.date_start
        return getattr(wo.production_id, 'date_finished', False)

    def _responsable(self, wo):
        if getattr(wo, 'time_ids', False) and wo.time_ids:
            last = wo.time_ids.sorted(lambda t: t.date_end or t.date_start)[-1]
            if last.user_id:
                return last.user_id.name
        if getattr(wo.production_id, 'user_id', False):
            return wo.production_id.user_id.name
        return '-'

    # ---------- vistas ----------
    @http.route('/wo/<int:wo_id>', type='http', auth='user', methods=['GET'], csrf=False)
    def wo_form(self, wo_id, **kw):
        wo = request.env['mrp.workorder'].sudo().browse(wo_id)
        if not wo.exists():
            raise NotFound()

        if wo.state == 'done':
            msg = _(
                "Orden de trabajo: %(wo)s\n\n"
                "Producto: %(prod)s\n"
                "MO: %(mo)s\n"
                "Responsable: %(user)s\n"
                "Estado: Terminada\n"
                "Fecha/hora de cierre: %(dt)s\n\n"
                "Esta orden ya fue finalizada. No se puede volver a cargar."
            ) % {
                'wo': wo.name,
                'prod': wo.product_id.display_name,
                'mo': wo.production_id.name,
                'user': self._responsable(wo),
                'dt': _fmt_dt(self._wo_close_dt(wo)),
            }
            return request.render('mrp_work_queue.wo_finish_result', {'ok': False, 'message': msg})

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
                'ok': False, 'message': _("La orden no existe.")
            })

        # Bloqueo si ya está done
        if wo.state == 'done':
            msg = _("Esta orden ya estaba finalizada. Cierre: %s") % _fmt_dt(self._wo_close_dt(wo))
            return request.render('mrp_work_queue.wo_finish_result', {'ok': True, 'message': msg})

        ok_qty  = _to_float(post.get('ok_qty'))
        rej_qty = _to_float(post.get('rej_qty'))
        if ok_qty < 0: ok_qty = 0.0
        if rej_qty < 0: rej_qty = 0.0
        total_qty = ok_qty + rej_qty

        try:
            # 1) Poner la WO en progreso
            if wo.state not in ('progress', 'done'):
                if hasattr(wo, 'button_start'):
                    wo.button_start()
                elif hasattr(wo, 'action_start'):
                    wo.action_start()

            # 2) Registrar producción (OK + Rechazo) usando la API oficial
            if total_qty > 0:
                if hasattr(wo, 'record_production'):
                    wo.qty_producing = total_qty
                    wo.record_production()
                elif hasattr(wo, 'button_finish'):
                    wo.qty_producing = total_qty
                    wo.button_finish()

            # 3) Scrap de rechazadas (validado en firme)
            if rej_qty > 0:
                Scrap = env['stock.scrap'].sudo()
                # campo destino que exista en esta versión
                dest_field = 'scrap_location_id' if 'scrap_location_id' in Scrap._fields else (
                             'location_dest_id' if 'location_dest_id' in Scrap._fields else None)

                # ubicación de scrap
                scrap_loc = env.ref('stock.stock_location_scrapped', raise_if_not_found=False) \
                            or env.ref('stock.location_scrapped', raise_if_not_found=False)
                if not scrap_loc:
                    scrap_loc = env['stock.location'].sudo().search([('scrap_location', '=', True)], limit=1)

                if dest_field and scrap_loc:
                    src_loc = wo.production_id.location_dest_id or env.ref('stock.stock_location_stock').sudo()
                    vals = {
                        'product_id': wo.product_id.id,
                        'product_uom_id': (wo.product_uom_id.id if wo.product_uom_id else wo.product_id.uom_id.id),
                        'scrap_qty': rej_qty,
                        'company_id': wo.company_id.id,
                        'origin': 'MO %s / WO %s' % (wo.production_id.name, wo.name),
                        'location_id': src_loc.id,
                    }
                    if 'production_id' in Scrap._fields:
                        vals['production_id'] = wo.production_id.id
                    vals[dest_field] = scrap_loc.id

                    scrap = Scrap.create(vals)
                    # validar (algunas versiones usan action_validate, otras action_done)
                    if hasattr(scrap, 'action_validate'):
                        scrap.action_validate()
                    elif hasattr(scrap, 'action_done'):
                        scrap.action_done()
                else:
                    _logger.warning("No se pudo determinar ubicación/campo de destino para scrap; se omite.")

            # 4) Cerrar la WO
            if wo.state != 'done':
                if hasattr(wo, 'button_finish'):
                    wo.button_finish()
                elif hasattr(wo, 'action_done'):
                    wo.action_done()

            # 5) Intentar cerrar la MO sin mirar cantidades: sólo estados.
            mo = wo.production_id
            if mo and mo.state != 'done':
                all_wos_done = all(w.state == 'done' for w in mo.workorder_ids)
                # si quedan movimientos en estado distinto a done/cancel, no cerramos
                raw_pending = any(m.state not in ('done', 'cancel') for m in mo.move_raw_ids)
                fin_pending = any(m.state not in ('done', 'cancel') for m in mo.move_finished_ids)
                if all_wos_done and not raw_pending and not fin_pending:
                    if hasattr(mo, 'button_mark_done'):
                        try:
                            mo.button_mark_done()
                        except Exception:
                            _logger.info("No se pudo cerrar la MO %s automáticamente.", mo.name)
                    elif hasattr(mo, 'action_done'):
                        try:
                            mo.action_done()
                        except Exception:
                            _logger.info("No se pudo cerrar la MO %s automáticamente.", mo.name)

            msg = _("Orden finalizada. OK: %(ok).2f, Rechazo: %(rej).2f. Cierre: %(dt)s") % {
                'ok': ok_qty, 'rej': rej_qty, 'dt': _fmt_dt(self._wo_close_dt(wo)),
            }
            return request.render('mrp_work_queue.wo_finish_result', {'ok': True, 'message': msg})

        except Exception as e:
            _logger.exception("Error finalizando WO %s", wo.name)
            return request.render('mrp_work_queue.wo_finish_result', {
                'ok': False, 'message': _("Error al finalizar: %s") % (str(e),)
            })
