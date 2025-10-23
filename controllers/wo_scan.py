# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from werkzeug.exceptions import NotFound
from datetime import datetime
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


def _fmt_dt(dt):
    # dt ya viene en UTC. Si querés TZ del usuario, habría que convertir.
    return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else '-'


class WoScanController(http.Controller):

    # ---------- utilitarios de lectura ----------
    def _get_wo_close_dt(self, wo):
        """Fecha/hora de cierre de la OT."""
        # Odoo 16/17 suele guardar en time_ids; si no, usá date_finished de la MO
        if wo and hasattr(wo, 'time_ids') and wo.time_ids:
            last = wo.time_ids.sorted(lambda t: t.date_end or t.date_start)[-1]
            return last.date_end or last.date_start
        return getattr(wo.production_id, 'date_finished', False)

    def _get_responsable(self, wo):
        """Responsable (último usuario que registró tiempo o el de la MO)."""
        if wo and hasattr(wo, 'time_ids') and wo.time_ids:
            last = wo.time_ids.sorted(lambda t: t.date_end or t.date_start)[-1]
            if last.user_id:
                return last.user_id.name
        if getattr(wo.production_id, 'user_id', False):
            return wo.production_id.user_id.name
        return '-'

    def _get_already_done_numbers(self, wo):
        """Devuelve (producido_total, scrap_hecho) a partir de movimientos/scraps."""
        # Producido total (lo que efectivamente entró a stock por la MO)
        produced = 0.0
        prod = wo.production_id
        # finished moves confirmados a stock
        for mv in prod.move_finished_ids.filtered(lambda m: m.state == 'done'):
            produced += mv.quantity

        # scrap hecho para ese producto y MO
        scrap_done = 0.0
        Scrap = request.env['stock.scrap'].sudo()
        domain = [('product_id', '=', wo.product_id.id), ('state', '=', 'done')]
        # algunas versiones guardan production_id en scrap
        if 'production_id' in Scrap._fields and prod:
            domain.append(('production_id', '=', prod.id))
        else:
            # fallback: por si no está el campo production_id, usamos origin
            domain.append(('origin', 'ilike', prod.name if prod else 'MO '))

        for sc in Scrap.search(domain):
            scrap_done += sc.scrap_qty
        return produced, scrap_done

    # ---------- vistas ----------
    @http.route('/wo/<int:wo_id>', type='http', auth='user', methods=['GET'], csrf=False)
    def wo_form(self, wo_id, **kw):
        wo = request.env['mrp.workorder'].sudo().browse(wo_id)
        if not wo.exists():
            raise NotFound()

        # Si la OT ya está cerrada, mostramos panel de info y NO permitimos cargar
        already_done = (wo.state == 'done')

        produced, scrapped = self._get_already_done_numbers(wo) if already_done else (0.0, 0.0)
        close_dt = self._get_wo_close_dt(wo) if already_done else False

        values = {
            'wo': wo,
            'product': wo.product_id,
            'title': _("Orden de trabajo: %s") % (wo.name,),
            'ok_default': "",
            'rej_default': "0",
            'already_done': already_done,
            'mo_name': wo.production_id.name,
            'responsable_name': self._get_responsable(wo),
            'produced_total': produced,
            'scrap_total': scrapped,
            'close_dt': _fmt_dt(close_dt) if close_dt else '-',
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

        # si ya está done, no re-procesar
        if wo.state == 'done':
            produced, scrapped = self._get_already_done_numbers(wo)
            msg = _("Esta orden ya estaba finalizada. Producido: %(ok).2f, Scrap: %(rej).2f") % {
                'ok': produced, 'rej': scrapped
            }
            return request.render('mrp_work_queue.wo_finish_result', {'ok': True, 'message': msg})

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

            # 3) SCRAP de rechazadas (validado)
            if rej_qty > 0:
                Scrap = env['stock.scrap'].sudo()

                # campo destino que exista en tu versión
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
                        'product_uom_id': wo.product_uom_id.id,
                        'scrap_qty': rej_qty,
                        'company_id': wo.company_id.id,
                        'origin': 'MO %s / WO %s' % (wo.production_id.name, wo.name),
                        'location_id': src_loc.id,
                        'production_id': wo.production_id.id if 'production_id' in Scrap._fields else False,
                    }
                    vals[dest_field] = scrap_loc.id
                    scrap = Scrap.create(vals)
                    # validar en firme
                    scrap.action_validate()
                    # en algunas versiones action_validate ya deja state='done'
                    if getattr(scrap, 'state', 'done') != 'done':
                        _logger.warning("Scrap quedó en estado %s", getattr(scrap, 'state', '?'))
                else:
                    _logger.warning("No se pudo determinar ubicación/campo de destino para scrap; se omite.")

            # 4) Cerrar la OT
            if wo.state != 'done':
                if hasattr(wo, 'button_finish'):
                    wo.button_finish()
                elif hasattr(wo, 'action_done'):
                    wo.action_done()

            # 5) (Opcional) si todas las WOs de la MO están done, intentar cerrar la MO
            mo = wo.production_id
            if mo and all(w.state == 'done' for w in mo.workorder_ids):
                # si no hay consumos pendientes, cerramos
                pending_consumptions = any(
                    mv.state not in ('done', 'cancel') and mv.product_uom_qty and (mv.quantity_done < mv.product_uom_qty)
                    for mv in mo.move_raw_ids
                )
                if not pending_consumptions and hasattr(mo, 'button_mark_done'):
                    try:
                        mo.button_mark_done()
                    except Exception:
                        # si algo impide cerrar la MO, no cortamos el flujo
                        _logger.info("No se pudo cerrar la MO %s automáticamente.", mo.name)

            close_dt = self._get_wo_close_dt(wo)
            msg = _("Orden finalizada. OK: %(ok).2f, Rechazo: %(rej).2f. Cierre: %(dt)s") % {
                'ok': ok_qty, 'rej': rej_qty, 'dt': _fmt_dt(close_dt)
            }
            return request.render('mrp_work_queue.wo_finish_result', {'ok': True, 'message': msg})

        except Exception as e:
            _logger.exception("Error finalizando WO %s", wo.name)
            return request.render('mrp_work_queue.wo_finish_result', {
                'ok': False,
                'message': _("Error al finalizar: %s") % (str(e),)
            })