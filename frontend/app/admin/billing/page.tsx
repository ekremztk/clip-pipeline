import { Plus } from "lucide-react";

import { invoices } from "../_components/admin-data";
import { Button, PageHeader, SectionCard, SectionHeader, SimpleTable, StatusBadge } from "../_components/admin-ui";

function tone(status: string) {
    if (status === "paid") return "success" as const;
    if (status === "open") return "warning" as const;
    if (status === "internal") return "neutral" as const;
    return "danger" as const;
}

export default function BillingPage() {
    return (
        <>
            <PageHeader title="Billing" description="Invoices, API customer payments, managed service accounts, and overdue checks." action={<Button><Plus size={16} />New invoice</Button>} />
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                <SectionCard className="p-4">
                    <p className="text-sm text-[#737373]">Paid this month</p>
                    <p className="mt-2 text-3xl font-bold text-[#171717]">$0.00</p>
                    <p className="mt-1 text-xs text-[#737373]">No invoices synced</p>
                </SectionCard>
                <SectionCard className="p-4">
                    <p className="text-sm text-[#737373]">Open balance</p>
                    <p className="mt-2 text-3xl font-bold text-[#171717]">$0.00</p>
                    <p className="mt-1 text-xs text-[#737373]">No open invoices</p>
                </SectionCard>
                <SectionCard className="p-4">
                    <p className="text-sm text-[#737373]">Internal usage</p>
                    <p className="mt-2 text-3xl font-bold text-[#171717]">$0.00</p>
                    <p className="mt-1 text-xs text-[#737373]">No API usage synced</p>
                </SectionCard>
            </div>
            <SectionCard className="mt-6 overflow-hidden">
                <SectionHeader title="Invoices" description="Payment status and billing records" />
                {invoices.length === 0 ? (
                    <div className="p-6 text-sm text-[#737373]">No invoices created yet.</div>
                ) : (
                    <SimpleTable
                        columns={["Invoice", "Customer", "Amount", "Due", "Status"]}
                        rows={invoices.map((invoice) => [
                            <span className="font-medium text-[#171717]" key="invoice">{invoice.number}</span>,
                            invoice.customer,
                            invoice.amount,
                            invoice.due,
                            <StatusBadge key="status" tone={tone(invoice.status)}>{invoice.status}</StatusBadge>,
                        ])}
                    />
                )}
            </SectionCard>
        </>
    );
}
