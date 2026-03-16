"use client";

import { motion } from "framer-motion";
import { Brain } from "lucide-react";

export default function MemoryPage() {
    return (
        <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="flex flex-col items-center justify-center h-full text-center py-20"
        >
            <div className="w-16 h-16 mb-4 rounded-full bg-white/[0.03] flex items-center justify-center border border-white/[0.06]">
                <Brain className="w-6 h-6 text-[#6b7280]" />
            </div>
            <h2 className="text-xl font-semibold mb-2 capitalize text-white">Channel Memory</h2>
            <p className="text-[#6b7280] text-sm max-w-sm">
                Channel Memory — Coming Soon
            </p>
        </motion.div>
    );
}