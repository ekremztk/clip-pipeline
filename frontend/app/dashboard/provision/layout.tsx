import { ClientRestricted } from "../client-guard";

export default function ProvisionLayout({ children }: { children: React.ReactNode }) {
    return <ClientRestricted>{children}</ClientRestricted>;
}
