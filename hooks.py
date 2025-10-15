# hooks.py
from odoo import api, SUPERUSER_ID

def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Plan = env["work.queue.plan"].sudo()
    Item = env["work.queue.item"].sudo()

    # 1) Backfill company_id si faltara
    plans_wo_company = Plan.search([("company_id", "=", False)])
    if plans_wo_company:
        plans_wo_company.write({"company_id": env.company.id})
    
    paper = env.ref('mrp_work_queue.paperformat_workorder_80mm', raise_if_not_found=False)
    if paper:
        # 2) localizar el reporte de OT por report_name (no por xmlid)
        report = env['ir.actions.report'].search(
            [('report_name', '=', 'mrp.report_mrp_workorder')], limit=1
        )
        if report and report.paperformat_id != paper:
            report.paperformat_id = paper.id
    
    # 2) Fusionar duplicados por (workcenter_id, employee_id, company_id)
    cr.execute("""
        SELECT array_agg(id ORDER BY id) AS ids
        FROM work_queue_plan
        GROUP BY workcenter_id, employee_id, company_id
        HAVING COUNT(*) > 1
    """)
    for ids_tuple in cr.fetchall():
        ids = ids_tuple[0] or []
        if len(ids) < 2:
            continue
        keep, drop = ids[0], ids[1:]
        Item.search([("plan_id", "in", drop)]).write({"plan_id": keep})
        Item.search([("plan_backlog_helper_id", "in", drop)]).write({"plan_backlog_helper_id": keep})
        Plan.browse(drop).unlink()

    # 3) Garantizar el UNIQUE en DB (si aún no existe)
    cr.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uniq_wc_emp_company'
                  AND conrelid = 'work_queue_plan'::regclass
            ) THEN
                BEGIN
                    ALTER TABLE work_queue_plan
                    ADD CONSTRAINT uniq_wc_emp_company
                    UNIQUE (workcenter_id, employee_id, company_id);
                EXCEPTION WHEN unique_violation THEN
                    -- En caso muy raro: volver a intentar tras limpieza
                    -- (para instalaciones “sucias” preexistentes)
                    -- No hacemos nada: el constraint ya existe en esencia.
                    NULL;
                END;
            END IF;
        END $$;
    """)
