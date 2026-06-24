'use client';

import { Shield } from "lucide-react";

export default function AccessDenied() {
    return (
        <div className="flex-1 flex items-center justify-center">
            <div className="text-center max-w-sm">
                <div
                    className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-5"
                    style={{ background: "rgba(250,249,245,0.05)" }}
                >
                    <Shield size={24} style={{ color: "#ababab" }} />
                </div>
                <h2 className="text-lg font-semibold mb-2" style={{ color: "#faf9f5" }}>
                    Access Denied
                </h2>
                <p className="text-sm" style={{ color: "#ababab" }}>
                    You don't have permission to access this page. Please contact your administrator.
                </p>
            </div>
        </div>
    );
}
