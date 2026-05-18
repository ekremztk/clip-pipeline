import { Plus } from "lucide-react";

import { customers } from "../_components/admin-data";
import { Button, PageHeader, PersonCell, SearchToolbar, SectionCard, SectionHeader, SimpleTable, StatusBadge } from "../_components/admin-ui";

function tone(status: string) {
    if (status === "active") return "success" as const;
    if (status === "lead") return "info" as const;
    if (status === "paused") return "warning" as const;
    return "neutral" as const;
}

export default function CustomersPage() {
    return (
        <>
            <PageHeader title="Customers" description="Creator, agency, and managed-service accounts for Prognot." action={<Button><Plus size={16} />New customer</Button>} />
            <div className="mb-4">
                <SearchToolbar placeholder="Search customers..." />
            </div>
            <SectionCard className="overflow-hidden">
                <SectionHeader title="Customer Directory" description="Channels and agencies that use Prognot as a service or API" />
                {customers.length === 0 ? (
                    <div className="p-6 text-sm text-[#737373]">No customers connected yet.</div>
                ) : (
                    <SimpleTable
                        columns={["Customer", "Plan", "Revenue", "Clips", "Status"]}
                        rows={customers.map((customer, index) => [
                            <PersonCell key="customer" initials={customer.name.slice(0, 2).toUpperCase()} title={customer.name} subtitle={customer.contact} color={["#0369a1", "#047857", "#4f46e5", "#b45309"][index]} />,
                            customer.plan,
                            customer.revenue,
                            customer.clips,
                            <StatusBadge key="status" tone={tone(customer.status)}>{customer.status}</StatusBadge>,
                        ])}
                    />
                )}
            </SectionCard>
        </>
    );
}
