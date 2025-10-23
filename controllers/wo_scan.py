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
    return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else '-'


def _qty_done(move):
    """Cantidad hecha para un stock.move, compatible con distintas versiones."""
    # Algunas versiones tienen quantity_done en el move
    q = getattr(move, 'quantity_done', None)
    if q is not None:
        return q or 0.0
    # Fallback genérico: sumar las move lines
    return sum(ml.qty_done or 0.0 for ml in move.move_line_ids)


class WoScanController(http.Controller):

    # ---------- utilitarios de lectura ----------
    def _get_wo_close_dt(self, wo):
        if wo and hasattr(wo, 'time_ids') and wo.time_ids:
            last = wo.time_ids.sorted(lambda t: t.date_end or t.date_start)[-1]
            return last.date_end or last.date_start
        return getattr(wo.production_id, 'date_finished', False)

    def _get_responsable(self, wo):
        if wo and hasattr(wo, 'time_ids') and wo.time_ids:
            last = wo.time_ids.sorted(lambda t: t.date_end or t.date_start)[-1]
            if last.user_id:
                return last.user_id.name
        if getattr(wo.production_id, 'user_id', False):
            return wo.production_id.user_id.name
        return '-'

    def _get_already_done_numbers(self, wo):
        produced = 0.0
        prod = wo.production_id
        for mv in prod.move_finished_ids.filtered(lambda m: m.state == 'done'):
            # quantity a veces guarda lo movido (en done)
            produced += getattr(mv, 'quantity', 0.0) or _qty_done(mv)
        scrap_done = 0.0
        Scrap = request.env['stock.scrap'].sudo()
        domain = [('product_id', '=', wo.product_id.id), ('state', '=', 'done')]
        if 'production_id' in Scrap._fields and prod:
            domain.append(('production_id', '=', prod.id))
        else:
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

            # 2) Producir TODO (OK + rechazadas)
            if total_qty > 0:
                if hasattr(wo, 'record_production'):
                    wo.qty_producing = total_qty
                    wo.record_production()
                elif hasattr(wo, 'button_finish'):
                    wo.qty_producing = total_qty
                    wo.button_finish()
                # Sin fallback directo a moves — mantenemos el flujo oficial y robusto

            # 3) SCRAP de rechazadas (desde el terminado)
            if rej_qty > 0:
                Scrap = env['stock.scrap'].sudo()
                dest_field = 'scrap_location_id' if 'scrap_location_id' in Scrap._fields else (
                             'location_dest_id' if 'location_dest_id' in Scrap._fields else None)
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
                    }
                    if 'production_id' in Scrap._fields:
                        vals['production_id'] = wo.production_id.id
                    vals[dest_field] = scrap_loc.id
                    scrap = Scrap.create(vals)
                    scrap.action_validate()
                else:
                    _logger.warning("No se pudo determinar ubicación/campo de destino para scrap; se omite.")

            # 4) Cerrar la OT
            if wo.state != 'done':
                if hasattr(wo, 'button_finish'):
                    wo.button_finish()
                elif hasattr(wo, 'action_done'):
                    wo.action_done()

            # 5) Intentar cerrar la MO SOLO si no queda nada pendiente
            mo = wo.production_id
            if mo and all(w.state == 'done' for w in mo.workorder_ids):
                raw_pending = any(
                    mv.state not in ('done', 'cancel') and _qty_done(mv) < (mv.product_uom_qty or 0.0)
                    for mv in mo.move_raw_ids
                )
                finished_pending = any(
                    mv.state not in ('done', 'cancel') and _qty_done(mv) < (mv.product_uom_qty or 0.0)
                    for mv in mo.move_finished_ids
                )
                if not raw_pending and not finished_pending and hasattr(mo, 'button_mark_done'):
                    try:
                        mo.button_mark_done()
                    except Exception:
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
