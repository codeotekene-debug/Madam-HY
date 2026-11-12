/**
 * MADAM HY - Credits list interactions.
 * Production-grade credit accounts browsing, filtering, and real-time ledger tracking.
 */

(function () {
    'use strict';

    let creditsData = [];

    async function initCredits() {
        await loadCreditsData();
        bindCreditsFilters();
    }

    async function loadCreditsData() {
        const creditsDataEl = document.getElementById('creditsDataJson');
        if (creditsDataEl && creditsDataEl.textContent.trim()) {
            try {
                creditsData = JSON.parse(creditsDataEl.textContent);
                renderCreditsSummary();
                renderCreditsTable();
                return;
            } catch (e) {
                console.error('Failed to parse credits JSON from DOM:', e);
            }
        }

        // Fallback: fetch from API
        try {
            const resp = await fetch('/credits/?format=json');
            if (resp.ok) {
                const json = await resp.json();
                creditsData = (json.data && json.data.accounts) || [];
                renderCreditsSummary();
                renderCreditsTable();
            }
        } catch (e) {
            console.error('Failed to fetch credits from API:', e);
        }
    }

    function bindCreditsFilters() {
        const searchInput = document.getElementById('creditsSearch');
        const statusFilter = document.getElementById('creditsStatusFilter');

        const update = () => renderCreditsTable();

        searchInput?.addEventListener('input', update);
        statusFilter?.addEventListener('change', update);
    }

    function renderCreditsSummary() {
        const totalIssued = document.getElementById('totalCreditIssued');
        const totalOutstanding = document.getElementById('totalOutstanding');
        const totalOverdue = document.getElementById('totalOverdue');
        const totalAccounts = document.getElementById('totalAccountsCount');

        if (!creditsData.length) return;

        const totalLimit = creditsData.reduce((sum, c) => sum + (Number(c.credit_limit || c.creditLimit) || 0), 0);
        const outstanding = creditsData.reduce((sum, c) => sum + (Number(c.outstanding_balance || c.outstandingBalance) || 0), 0);
        const overdue = creditsData
            .filter(c => c.is_overdue || c.isOverdue)
            .reduce((sum, c) => sum + (Number(c.outstanding_balance || c.overdueAmount) || 0), 0);

        if (totalIssued) totalIssued.textContent = `₦ ${formatCurrency(totalLimit)}`;
        if (totalOutstanding) totalOutstanding.textContent = `₦ ${formatCurrency(outstanding)}`;
        if (totalOverdue) totalOverdue.textContent = `₦ ${formatCurrency(overdue)}`;
        if (totalAccounts) totalAccounts.textContent = String(creditsData.length);
    }

    function renderCreditsTable() {
        const tableBody = document.getElementById('creditsTableBody');
        const emptyState = document.getElementById('creditsEmptyState');
        const searchInput = document.getElementById('creditsSearch');
        const statusFilter = document.getElementById('creditsStatusFilter');

        if (!tableBody) return;

        const query = searchInput?.value.trim().toLowerCase() || '';
        const statusValue = (statusFilter?.value || 'all').toLowerCase();

        let filtered = creditsData.filter(credit => {
            const customerName = (credit.customer?.full_name || credit.customer?.username || (typeof credit.customer === 'string' ? credit.customer : '') || '').toLowerCase();
            const phone = (credit.customer?.phone_number || credit.phone || '').toLowerCase();
            const email = (credit.customer?.email || '').toLowerCase();
            const status = (credit.status_display || credit.status || '').toLowerCase();

            const matchesQuery = !query || customerName.includes(query) || phone.includes(query) || email.includes(query);
            let matchesStatus = (statusValue === 'all');
            if (!matchesStatus) {
                matchesStatus = status.includes(statusValue);
            }
            return matchesQuery && matchesStatus;
        });

        if (!filtered.length) {
            tableBody.innerHTML = '';
            emptyState?.classList.remove('empty-state-hidden');
            return;
        }

        emptyState?.classList.add('empty-state-hidden');
        tableBody.innerHTML = filtered.map(credit => {
            const custName = credit.customer?.full_name || credit.customer?.username || (typeof credit.customer === 'string' ? credit.customer : 'Walk-in Customer');
            const custPhone = credit.customer?.phone_number || credit.phone || '-';
            const creditLimit = Number(credit.credit_limit || credit.creditLimit) || 0;
            const outstanding = Number(credit.outstanding_balance || credit.outstandingBalance) || 0;
            const available = credit.available_credit != null ? Number(credit.available_credit) : Math.max(0, creditLimit - outstanding);
            const statusDisplay = credit.status_display || credit.status || 'Active';
            const statusClass = statusDisplay.toLowerCase().replace(/\s+/g, '-');
            const dueDate = credit.next_due_date || credit.dueDate;
            const custId = credit.customer?.id || '';

            return `
                <tr>
                    <td data-label="Customer">
                        <strong>${escapeHtml(custName)}</strong>
                        ${credit.customer?.email ? `<div style="font-size: 11px; color: var(--muted);">${escapeHtml(credit.customer.email)}</div>` : ''}
                    </td>
                    <td data-label="Phone">${escapeHtml(custPhone)}</td>
                    <td data-label="Credit Limit" class="num">₦ ${formatCurrency(creditLimit)}</td>
                    <td data-label="Used" class="num">₦ ${formatCurrency(outstanding)}</td>
                    <td data-label="Available" class="num" style="color: var(--primary); font-weight: 600;">₦ ${formatCurrency(available)}</td>
                    <td data-label="Outstanding" class="num" style="color: ${outstanding > 0 ? 'var(--warning-dark, #b87700)' : 'var(--muted)'};">₦ ${formatCurrency(outstanding)}</td>
                    <td data-label="Due Date">${dueDate ? formatDate(dueDate) : '-'}</td>
                    <td data-label="Status"><span class="status-pill ${statusClass}">${escapeHtml(statusDisplay)}</span></td>
                    <td data-label="Action" style="text-align: right; white-space: nowrap;">
                        <a href="/credits/accounts/${encodeURIComponent(credit.id)}/" class="action-link">View</a>
                        ${custId ? `<a href="/credits/customers/add-credit/?customer_id=${encodeURIComponent(custId)}" class="action-link" style="margin-left: 8px; color: var(--primary);" title="Provision or Top Up Credit">+Credit</a>` : ''}
                    </td>
                </tr>
            `;
        }).join('');
    }

    function formatDate(value) {
        if (!value) return '-';
        const d = new Date(value);
        if (isNaN(d.getTime())) return String(value);
        return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
    }

    function formatCurrency(value) {
        const num = Number(value) || 0;
        return num.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCredits);
    } else {
        initCredits();
    }
    window.addEventListener('page:load', initCredits);
})();
