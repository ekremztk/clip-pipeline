import { ClientRestricted } from "../client-guard";

export default function StudioLayout({ children }: { children: React.ReactNode }) {
    return <ClientRestricted>{children}</ClientRestricted>;
}
