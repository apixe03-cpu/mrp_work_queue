/** @odoo-module **/

import { registry } from "@web/core/registry";
import { KanbanController } from "@web/views/kanban/kanban_controller";

class DualKanbanController extends KanbanController {
    async onRecordDropped(source, target, { fromList, toList, record }) {
        try {
            const fromType = fromList?.props?.ArchInfo?.options?.mrp_dual_kanban;
            const toType   = toList?.props?.ArchInfo?.options?.mrp_dual_kanban;

            // No es nuestro caso o se cayó en la misma lista → default
            if (!fromType || !toType || fromType === toType) {
                return super.onRecordDropped(...arguments);
            }

            const planEmployeeId = this.model.root.context.plan_employee_id;

            const recId = record.resId;
            const values = {};
            if (toType === "employee") {
                if (!planEmployeeId) return;
                values.employee_id = planEmployeeId;
                values.plan_id = this.model.root.resId;
            } else if (toType === "backlog") {
                values.employee_id = false;
                // al volver a backlog, lo sacamos de la cola del plan
                values.plan_id = false;
            }

            await this.model.orm.write("work.queue.item", [recId], values);
            await this.model.load();
            this.render(true);
        } catch (e) {
            // fallback
            return super.onRecordDropped(...arguments);
        }
    }
}

// Registramos una variante de vista kanban para nuestro tablero
registry.category("views").add("mrp_dual_kanban", {
    ...registry.category("views").get("kanban"),
    Controller: DualKanbanController,
});