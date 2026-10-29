document.addEventListener('DOMContentLoaded', () => {
    const body = document.getElementById('vouchers-body');
    const alertBox = document.getElementById('voucher-alert');
    const modal = document.getElementById('voucher-modal');
    const form = document.getElementById('voucher-form');
    const typeInput = document.getElementById('discount-type');
    const valueInput = document.getElementById('discount-value');
    const valueGroup = document.getElementById('discount-value-group');
    const valueHelp = document.getElementById('discount-help');

    const token = () => localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
    const headers = () => {
        const value = token();
        return value ? { Authorization: `Bearer ${value}` } : {};
    };

    function showAlert(message, type) {
        alertBox.textContent = message;
        alertBox.className = `voucher-alert voucher-alert-${type}`;
        alertBox.hidden = false;
    }

    function apiError(data, fallback) {
        return data && data.error && data.error.message ? data.error.message : fallback;
    }

    function redirectToLogin() {
        localStorage.removeItem('access_token');
        sessionStorage.removeItem('access_token');
        window.location.href = '/login?next=/seller/vouchers';
    }

    async function apiRequest(url, options = {}) {
        const response = await fetch(url, {
            ...options,
            headers: { Accept: 'application/json', ...headers(), ...(options.headers || {}) },
        });
        const data = await response.json().catch(() => null);
        if (response.status === 401) {
            redirectToLogin();
            return null;
        }
        if (!response.ok) throw new Error(apiError(data, 'The server could not complete the request.'));
        return data;
    }

    function formatMoney(value) {
        return `${Number(value).toLocaleString('vi-VN')} ₫`;
    }

    function escapeHtml(value) {
        return String(value).replace(/[&<>"']/g, (character) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;',
        }[character]));
    }

    function formatDiscount(voucher) {
        if (voucher.discount_type === 'FREE_SHIPPING') return 'Free shipping';
        if (voucher.discount_type === 'PERCENTAGE') {
            const percentage = (voucher.discount_value / 100).toFixed(2).replace(/\.?0+$/, '');
            return `${percentage}%${voucher.max_discount ? ` (cap ${formatMoney(voucher.max_discount)})` : ''}`;
        }
        return formatMoney(voucher.discount_value);
    }

    function render(vouchers) {
        body.replaceChildren();
        if (!vouchers.length) {
            const row = document.createElement('tr');
            row.innerHTML = '<td colspan="7" class="text-center text-muted">No shop vouchers found.</td>';
            body.appendChild(row);
            return;
        }
        vouchers.forEach((voucher) => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><strong>${escapeHtml(voucher.code)}</strong></td>
                <td>${formatDiscount(voucher)}</td>
                <td>${formatMoney(voucher.min_order_value)}</td>
                <td>${voucher.used_count} / ${voucher.usage_limit === null ? '∞' : voucher.usage_limit}</td>
                <td>${new Date(voucher.starts_at).toLocaleDateString()} - ${new Date(voucher.ends_at).toLocaleDateString()}</td>
                <td><span class="badge ${voucher.is_active ? 'badge-active' : 'badge-inactive'}">${voucher.is_active ? 'Active' : 'Inactive'}</span></td>
                <td><button class="btn btn-secondary btn-sm toggle-voucher" type="button">${voucher.is_active ? 'Deactivate' : 'Activate'}</button></td>
            `;
            row.querySelector('.toggle-voucher').addEventListener('click', () => toggle(voucher));
            body.appendChild(row);
        });
    }

    async function load() {
        if (!token()) {
            window.location.href = '/login?next=/seller/vouchers';
            return;
        }
        try {
            const data = await apiRequest('/api/v1/seller/vouchers');
            if (data === null) return;
            render(data);
        } catch (error) {
            body.innerHTML = `<tr><td colspan="7" class="text-center text-danger">${error.message}</td></tr>`;
        }
    }

    async function toggle(voucher) {
        try {
            const data = await apiRequest(`/api/v1/seller/vouchers/${voucher.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json', ...headers() },
                body: JSON.stringify({ is_active: !voucher.is_active }),
            });
            if (data === null) return;
            showAlert(`Voucher ${voucher.code} updated.`, 'success');
            await load();
        } catch (error) {
            showAlert(error.message, 'error');
        }
    }

    function updateDiscountFields() {
        const isShipping = typeInput.value === 'FREE_SHIPPING';
        valueGroup.hidden = isShipping;
        valueInput.required = !isShipping;
        valueInput.disabled = isShipping;
        valueHelp.textContent = typeInput.value === 'PERCENTAGE'
            ? 'Basis points: 1000 = 10%'
            : 'Amount in VND';
    }

    function openModal() {
        form.reset();
        const now = new Date();
        const later = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
        document.getElementById('starts-at').value = now.toISOString().slice(0, 16);
        document.getElementById('ends-at').value = later.toISOString().slice(0, 16);
        updateDiscountFields();
        modal.hidden = false;
    }

    document.getElementById('new-voucher-button').addEventListener('click', openModal);
    document.getElementById('cancel-voucher-button').addEventListener('click', () => { modal.hidden = true; });
    typeInput.addEventListener('change', updateDiscountFields);
    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const startsAt = new Date(document.getElementById('starts-at').value);
        const endsAt = new Date(document.getElementById('ends-at').value);
        if (startsAt >= endsAt) {
            showAlert('Voucher end date must be after start date.', 'error');
            return;
        }
        const type = typeInput.value;
        const payload = {
            code: document.getElementById('voucher-code').value.trim().toUpperCase(),
            discount_type: type,
            discount_value: type === 'FREE_SHIPPING' ? 0 : Number(valueInput.value),
            max_discount: document.getElementById('max-discount').value ? Number(document.getElementById('max-discount').value) : null,
            min_order_value: Number(document.getElementById('min-order-value').value || 0),
            usage_limit: document.getElementById('usage-limit').value ? Number(document.getElementById('usage-limit').value) : null,
            per_user_limit: document.getElementById('per-user-limit').value ? Number(document.getElementById('per-user-limit').value) : null,
            starts_at: startsAt.toISOString(),
            ends_at: endsAt.toISOString(),
            is_active: true,
        };
        try {
            const data = await apiRequest('/api/v1/seller/vouchers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...headers() },
                body: JSON.stringify(payload),
            });
            if (data === null) return;
            modal.hidden = true;
            showAlert(`Voucher ${payload.code} created.`, 'success');
            await load();
        } catch (error) {
            showAlert(error.message, 'error');
        }
    });

    load();
});
