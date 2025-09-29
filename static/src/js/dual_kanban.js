/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { KanbanController } from "@web/views/kanban/kanban_controller";

function getKanbanType(list) {
    try {
        // distintas variantes de cómo llega archInfo según versión/stack
        return (
            list?.props?.ArchInfo?.options?.mrp_dual_kanban ||
            list?.props?.archInfo?.options?.mrp_dual_kanban ||
            list?.props?.list?.archInfo?.options?.mrp_dual_kanban ||
            null
        );
    } catch (e) {
        return null;
    }
}

patch(KanbanController.prototype, "mrp_work_queue_dual_kanban", {
    async onRecordDropped(source, target, info) {
        try {
            const fromType = getKanbanType(info?.fromList);
            const toType   = getKanbanType(info?.toList);

            // Sólo intervenimos si es nuestro doble kanban y cambia de columna
            if (fromType && toType && fromType !== toType) {
                const recId = info?.record?.resId;
                const planEmployeeId =
                    this.model?.root?.context?.plan_employee_id ||
                    this.props?.context?.plan_employee_id;

                const values = {};
                if (toType === "employee") {
                    if (!planEmployeeId) {
                        return await super.onRecordDropped(...arguments);
                    }
                    values.employee_id = planEmployeeId;
                    values.plan_id = this.model?.root?.resId || false;
                } else if (toType === "backlog") {
                    values.employee_id = false;
                    values.plan_id = false;
                }

                await this.model.orm.write("work.queue.item", [recId], values);
                await this.model.load();
                this.render(true);
                return; // ya manejamos nosotros
            }
        } catch (e) {
            // si algo falla, no rompemos el flujo normal
            // console.warn("mrp_work_queue drag error:", e);
        }
        // fallback normal
        return await super.onRecordDropped(...arguments);
    },
});
 