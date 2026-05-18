import { Plus } from "lucide-react";

import { adminUsers } from "../_components/admin-data";
import { Button, PageHeader, PersonCell, SearchToolbar, SectionCard, SectionHeader, SimpleTable, StatusBadge } from "../_components/admin-ui";

export default function UsersPage() {
    return (
        <>
            <PageHeader title="Users" description="Admin users, roles, system agents, and access control." action={<Button><Plus size={16} />Invite user</Button>} />
            <div className="mb-4">
                <SearchToolbar placeholder="Search users..." />
            </div>
            <SectionCard className="overflow-hidden">
                <SectionHeader title="Admin Access" description="Users allowed to access this internal panel" />
                {adminUsers.length === 0 ? (
                    <div className="p-6 text-sm text-[#737373]">Admin user list is not synced yet.</div>
                ) : (
                    <SimpleTable
                        columns={["User", "Role", "Status"]}
                        rows={adminUsers.map((user, index) => [
                            <PersonCell key="user" initials={user.name.slice(0, 2).toUpperCase()} title={user.name} subtitle={user.email} color={["#0369a1", "#047857", "#4f46e5"][index]} />,
                            user.role,
                            <StatusBadge key="status" tone={user.status === "active" ? "success" : "neutral"}>{user.status}</StatusBadge>,
                        ])}
                    />
                )}
            </SectionCard>
        </>
    );
}
