/** @odoo-module **/

import { registry } from "@web/core/registry";

const base = registry.category("views").get("kanban");

// Subclase que solo actúa si el kanban tiene options.mrp_dual_kanban
class DualKanbanController extends base.Controller {
    async onRecordDropped(source, target, info) {
        const { fromList, toList, record } = info || {};
        const fromType = fromList?.props?.ArchInfo?.options?.mrp_dual_kanban;
        const toType   = toList?.props?.ArchInfo?.options?.mrp_dual_kanban;

        if (!fromType || !toType || fromType === toType) {
            return super.onRecordDropped(...arguments);
        }

        const planEmployeeId = this.model.root.context.plan_employee_id;
        const recId = record.resId;
        const values = {};

        if (toType === "employee") {
            if (!planEmployeeId) return;
            values.employee_id = planEmployeeId;
            values.plan_id = this.model.root.resId || false;
        } else if (toType === "backlog") {
            values.employee_id = false;
            values.plan_id = false;
        }

        await this.model.orm.write("work.queue.item", [recId], values);
        await this.model.load();
        this.render(true);
    }
}

// Registramos nuestra variante sin romper el resto
registry.category("views").add("kanban", {
    ...base,
    Controller: DualKanbanController,
});
