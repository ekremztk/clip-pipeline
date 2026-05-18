import { PageHeader } from "../_components/admin-ui";
import YouTubeChannelsPanel from "./youtube-channels-panel";

export default function ChannelsPage() {
    return (
        <>
            <PageHeader title="Channels" description="Connected YouTube channels and real channel metadata." />
            <YouTubeChannelsPanel />
        </>
    );
}
