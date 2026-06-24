import { ClientRestricted } from "../client-guard";

export default function ContentFinderLayout({ children }: { children: React.ReactNode }) {
    return <ClientRestricted>{children}</ClientRestricted>;
}
