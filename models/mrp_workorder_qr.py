# -*- coding: utf-8 -*-
import base64
import io

from odoo import api, fields, models

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M
except Exception:
    qrcode = None


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    # Imagen PNG del QR en base64 (cacheado en DB)
    qr_code = fields.Binary(string="QR Code", compute="_compute_qr_code", store=True)

    # (opcional) Texto que codificamos en el QR, útil para depurar
    qr_text = fields.Char(string="QR text", compute="_compute_qr_text", store=False)

    def _qr_payload(self):
        """Qué texto metemos dentro del QR.
        De forma robusta ponemos la URL directa al form de la OT.
        """
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        return f"{base}/web#id={self.id}&model=mrp.workorder&view_type=form"

    def _compute_qr_text(self):
        for wo in self:
            wo.qr_text = wo._qr_payload()

    @api.depends("name", "product_id", "production_id", "state")
    def _compute_qr_code(self):
        for wo in self:
            if not qrcode:
                # Si falta la lib, no reventamos el reporte; queda vacío
                wo.qr_code = False
                continue

            payload = wo._qr_payload()
            qr = qrcode.QRCode(
                version=None,  # que ajuste automáticamente
                error_correction=ERROR_CORRECT_M,
                box_size=6,    # 6*~1px ≈ 6px por “módulo”; lo escalamos en QWeb
                border=2,      # márgen blanco, 2 bloques
            )
            qr.add_data(payload)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            wo.qr_code = base64.b64encode(buf.getvalue())
