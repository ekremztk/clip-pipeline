'use client';

import { useState, useEffect } from 'react';
import { CreditCard, Check, X, Plus, Lock, Unlock, RefreshCw } from 'lucide-react';
import { authFetch } from '@/lib/api';

type Client = {
    user_id: string;
    display_name: string;
    email: string;
    balance: number;
    is_locked: boolean;
    locked_reason: string | null;
    consecutive_failures: number;
    max_concurrent_jobs: number;
    storage_cap_bytes: number;
};

type CreditRequest = {
    id: string;
    user_id: string;
    email: string;
    amount_requested: number;
    status: string;
    admin_note: string | null;
    created_at: string;
};

type Transaction = {
    id: string;
    job_id: string | null;
    type: string;
    amount: number;
    balance_after: number;
    note: string;
    created_at: string;
};

export default function AdminCreditsPage() {
    const [clients, setClients] = useState<Client[]>([]);
    const [requests, setRequests] = useState<CreditRequest[]>([]);
    const [selectedClient, setSelectedClient] = useState<string | null>(null);
    const [transactions, setTransactions] = useState<Transaction[]>([]);
    const [topupAmount, setTopupAmount] = useState('');
    const [topupNote, setTopupNote] = useState('');
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [clientsRes, requestsRes] = await Promise.all([
                authFetch('/admin/clients'),
                authFetch('/admin/credit-requests?status_filter=pending'),
            ]);
            if (clientsRes.ok) {
                const data = await clientsRes.json();
                setClients(data.clients || []);
            }
            if (requestsRes.ok) {
                const data = await requestsRes.json();
                setRequests(data.requests || []);
            }
        } catch (err) {
            console.error('Failed to fetch credits data', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, []);

    const fetchTransactions = async (userId: string) => {
        setSelectedClient(userId);
        try {
            const res = await authFetch(`/admin/clients/${userId}/transactions`);
            if (res.ok) {
                const data = await res.json();
                setTransactions(data.transactions || []);
            }
        } catch {}
    };

    const handleTopup = async (userId: string) => {
        const amount = parseInt(topupAmount, 10);
        if (isNaN(amount) || amount < 1) return;
        try {
            const res = await authFetch('/admin/clients/topup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, amount, note: topupNote }),
            });
            if (res.ok) {
                setTopupAmount('');
                setTopupNote('');
                fetchData();
            }
        } catch {}
    };

    const handleDecision = async (requestId: string, action: 'approve' | 'reject') => {
        try {
            const res = await authFetch('/admin/credit-requests/decide', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ request_id: requestId, action }),
            });
            if (res.ok) fetchData();
        } catch {}
    };

    const handleLock = async (userId: string, lock: boolean) => {
        const endpoint = lock ? '/admin/clients/lock' : '/admin/clients/unlock';
        try {
            await authFetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, reason: '' }),
            });
            fetchData();
        } catch {}
    };

    const formatDate = (d: string) => new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    const formatGB = (bytes: number) => `${(bytes / (1024 ** 3)).toFixed(1)} GB`;

    if (loading) {
        return (
            <div className="p-8">
                <div className="animate-pulse space-y-4">
                    <div className="h-8 w-48 rounded" style={{ background: 'rgba(250,249,245,0.06)' }} />
                    <div className="h-64 rounded-xl" style={{ background: 'rgba(250,249,245,0.03)' }} />
                </div>
            </div>
        );
    }

    return (
        <div className="p-8 space-y-8 max-w-6xl">
            <div className="flex items-center justify-between">
                <h1 className="text-xl font-bold" style={{ color: '#faf9f5' }}>Credit Management</h1>
                <button
                    onClick={fetchData}
                    className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium transition-colors hover:bg-white/5"
                    style={{ color: '#ababab' }}
                >
                    <RefreshCw size={14} /> Refresh
                </button>
            </div>

            {/* Pending Requests */}
            {requests.length > 0 && (
                <section>
                    <h2 className="text-sm font-semibold uppercase tracking-wider mb-3" style={{ color: '#ababab' }}>
                        Pending Requests ({requests.length})
                    </h2>
                    <div className="space-y-2">
                        {requests.map((req) => (
                            <div
                                key={req.id}
                                className="flex items-center gap-4 px-4 py-3 rounded-xl"
                                style={{ background: 'rgba(250,249,245,0.03)', border: '1px solid rgba(250,249,245,0.05)' }}
                            >
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium truncate" style={{ color: '#faf9f5' }}>
                                        {req.email}
                                    </p>
                                    <p className="text-xs" style={{ color: '#ababab' }}>
                                        Requesting {req.amount_requested} credits &middot; {formatDate(req.created_at)}
                                    </p>
                                </div>
                                <button
                                    onClick={() => handleDecision(req.id, 'approve')}
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
                                    style={{ background: '#faf9f5', color: '#141413' }}
                                >
                                    <Check size={12} /> Approve
                                </button>
                                <button
                                    onClick={() => handleDecision(req.id, 'reject')}
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors hover:bg-red-500/20"
                                    style={{ color: '#ef4444', border: '1px solid rgba(239,68,68,0.3)' }}
                                >
                                    <X size={12} /> Reject
                                </button>
                            </div>
                        ))}
                    </div>
                </section>
            )}

            {/* Clients Table */}
            <section>
                <h2 className="text-sm font-semibold uppercase tracking-wider mb-3" style={{ color: '#ababab' }}>
                    Clients ({clients.length})
                </h2>
                {clients.length === 0 ? (
                    <p className="text-sm" style={{ color: '#ababab' }}>No client accounts yet.</p>
                ) : (
                    <div className="space-y-2">
                        {clients.map((client) => (
                            <div key={client.user_id}>
                                <div
                                    className="flex items-center gap-4 px-4 py-3 rounded-xl cursor-pointer transition-colors hover:bg-white/[0.03]"
                                    style={{ background: 'rgba(250,249,245,0.02)', border: '1px solid rgba(250,249,245,0.05)' }}
                                    onClick={() => fetchTransactions(client.user_id)}
                                >
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                            <p className="text-sm font-medium" style={{ color: '#faf9f5' }}>
                                                {client.display_name || client.email}
                                            </p>
                                            {client.is_locked && (
                                                <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: 'rgba(239,68,68,0.15)', color: '#ef4444' }}>
                                                    Locked
                                                </span>
                                            )}
                                        </div>
                                        <p className="text-xs" style={{ color: '#ababab' }}>
                                            {client.email} &middot; Failures: {client.consecutive_failures} &middot; Storage cap: {formatGB(client.storage_cap_bytes)}
                                        </p>
                                    </div>
                                    <div className="text-right">
                                        <p className="text-lg font-bold" style={{ color: client.balance <= 10 ? '#f59e0b' : '#faf9f5' }}>
                                            {client.balance}
                                        </p>
                                        <p className="text-[10px] uppercase" style={{ color: '#ababab' }}>credits</p>
                                    </div>
                                    <div className="flex items-center gap-1">
                                        <button
                                            onClick={(e) => { e.stopPropagation(); handleLock(client.user_id, !client.is_locked); }}
                                            className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors hover:bg-white/10"
                                            style={{ color: '#ababab' }}
                                            title={client.is_locked ? 'Unlock' : 'Lock'}
                                        >
                                            {client.is_locked ? <Unlock size={14} /> : <Lock size={14} />}
                                        </button>
                                    </div>
                                </div>

                                {/* Expanded: Topup + Transactions */}
                                {selectedClient === client.user_id && (
                                    <div
                                        className="ml-4 mt-2 p-4 rounded-xl space-y-4"
                                        style={{ background: 'rgba(250,249,245,0.02)', border: '1px solid rgba(250,249,245,0.04)' }}
                                    >
                                        {/* Quick Topup */}
                                        <div className="flex items-center gap-2">
                                            <input
                                                type="number"
                                                placeholder="Amount"
                                                value={topupAmount}
                                                onChange={(e) => setTopupAmount(e.target.value)}
                                                className="w-24 px-3 py-2 rounded-lg text-sm outline-none"
                                                style={{ background: '#000', border: '1px solid #262626', color: '#faf9f5' }}
                                            />
                                            <input
                                                type="text"
                                                placeholder="Note (optional)"
                                                value={topupNote}
                                                onChange={(e) => setTopupNote(e.target.value)}
                                                className="flex-1 px-3 py-2 rounded-lg text-sm outline-none"
                                                style={{ background: '#000', border: '1px solid #262626', color: '#faf9f5' }}
                                            />
                                            <button
                                                onClick={() => handleTopup(client.user_id)}
                                                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
                                                style={{ background: '#faf9f5', color: '#141413' }}
                                            >
                                                <Plus size={12} /> Topup
                                            </button>
                                        </div>

                                        {/* Transaction History */}
                                        {transactions.length > 0 && (
                                            <div>
                                                <p className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: '#ababab' }}>
                                                    Recent Transactions
                                                </p>
                                                <div className="space-y-1 max-h-60 overflow-y-auto">
                                                    {transactions.slice(0, 20).map((tx) => (
                                                        <div
                                                            key={tx.id}
                                                            className="flex items-center gap-3 px-3 py-2 rounded-lg text-xs"
                                                            style={{ background: 'rgba(250,249,245,0.02)' }}
                                                        >
                                                            <span
                                                                className="font-mono px-1.5 py-0.5 rounded text-[10px] uppercase"
                                                                style={{
                                                                    background: tx.type === 'topup' ? 'rgba(34,197,94,0.1)' : tx.type === 'refund' ? 'rgba(59,130,246,0.1)' : tx.type === 'reserve' ? 'rgba(245,158,11,0.1)' : 'rgba(250,249,245,0.05)',
                                                                    color: tx.type === 'topup' ? '#22c55e' : tx.type === 'refund' ? '#3b82f6' : tx.type === 'reserve' ? '#f59e0b' : '#ababab',
                                                                }}
                                                            >
                                                                {tx.type}
                                                            </span>
                                                            <span style={{ color: tx.amount >= 0 ? '#22c55e' : '#ef4444' }}>
                                                                {tx.amount >= 0 ? '+' : ''}{tx.amount}
                                                            </span>
                                                            <span className="flex-1 truncate" style={{ color: '#ababab' }}>{tx.note}</span>
                                                            <span style={{ color: '#666' }}>{formatDate(tx.created_at)}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </section>
        </div>
    );
}
