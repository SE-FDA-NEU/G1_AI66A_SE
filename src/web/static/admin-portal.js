/* Admin Portal JavaScript Controller */

document.addEventListener('DOMContentLoaded', async () => {
    let currentUser = null;
    let categoriesList = [];

    const elements = {
        unauthorizedBanner: document.getElementById('admin-unauthorized-banner'),
        portalContent: document.getElementById('admin-portal-content'),
        adminUserName: document.getElementById('admin-user-name'),
        logoutBtn: document.getElementById('admin-logout-btn'),
        alertBox: document.getElementById('admin-alert'),

        // Nav
        tabs: document.querySelectorAll('.nav-tab'),
        views: document.querySelectorAll('.tab-view'),

        // Catalog
        catalogSearch: document.getElementById('catalog-search'),
        catalogStatusFilter: document.getElementById('catalog-filter-status'),
        catalogTbody: document.getElementById('catalog-tbody'),

        // Categories
        categoriesTbody: document.getElementById('categories-tbody'),
        btnNewCategory: document.getElementById('btn-new-category'),
        modalCategory: document.getElementById('modal-category'),
        formCategory: document.getElementById('form-category'),
        categoryTitle: document.getElementById('modal-category-title'),
        categoryIdInput: document.getElementById('category-id'),
        categoryNameInput: document.getElementById('category-name'),
        categorySlugInput: document.getElementById('category-slug'),
        categoryParentSelect: document.getElementById('category-parent'),

        // Vouchers
        vouchersTbody: document.getElementById('vouchers-tbody'),
        btnNewVoucher: document.getElementById('btn-new-voucher'),
        modalVoucher: document.getElementById('modal-voucher'),
        formVoucher: document.getElementById('form-voucher'),
        voucherCode: document.getElementById('voucher-code'),
        voucherType: document.getElementById('voucher-type'),
        voucherVal: document.getElementById('voucher-val'),
        labelVoucherVal: document.getElementById('label-voucher-val'),
        voucherMax: document.getElementById('voucher-max'),
        voucherMin: document.getElementById('voucher-min'),
        voucherUsageLimit: document.getElementById('voucher-usage-limit'),
        voucherUserLimit: document.getElementById('voucher-user-limit'),
        voucherStarts: document.getElementById('voucher-starts'),
        voucherEnds: document.getElementById('voucher-ends'),

        // Users
        usersSearch: document.getElementById('users-search'),
        usersRoleFilter: document.getElementById('users-filter-role'),
        usersStatusFilter: document.getElementById('users-filter-status'),
        usersTbody: document.getElementById('users-tbody'),
        modalUser: document.getElementById('modal-user'),
        formUserStatus: document.getElementById('form-user-status'),
        userStatusId: document.getElementById('user-status-id'),
        userStatusDesc: document.getElementById('modal-user-desc'),
        userStatusSelect: document.getElementById('user-status-select'),
        userStatusReason: document.getElementById('user-status-reason'),
        userAuditsList: document.getElementById('user-audits-list'),

        // Disputes
        disputesFilterStatus: document.getElementById('disputes-filter-status'),
        disputesTbody: document.getElementById('disputes-tbody'),
        modalDispute: document.getElementById('modal-dispute'),
        disputeModalSummary: document.getElementById('dispute-modal-summary'),
        formDisputeDecision: document.getElementById('form-dispute-decision'),
        disputeDecisionId: document.getElementById('dispute-decision-id'),
        disputeAction: document.getElementById('dispute-action'),
        groupDisputeRestock: document.getElementById('group-dispute-restock'),
        disputeRestock: document.getElementById('dispute-restock'),
        disputeNotes: document.getElementById('dispute-notes'),
    };

    function getToken() {
        return localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
    }

    function authHeaders() {
        const token = getToken();
        return token ? { 'Authorization': `Bearer ${token}` } : {};
    }

    function showAlert(message, type = 'success') {
        elements.alertBox.textContent = message;
        elements.alertBox.className = `portal-alert portal-alert-${type}`;
        elements.alertBox.style.display = 'block';
        setTimeout(() => {
            elements.alertBox.style.display = 'none';
        }, 5000);
    }

    // Check Admin Authentication
    async function checkAuth() {
        const token = getToken();
        if (!token) {
            elements.unauthorizedBanner.style.display = 'block';
            elements.portalContent.style.display = 'none';
            return false;
        }

        try {
            const res = await fetch('/api/v1/auth/me', { headers: authHeaders() });
            if (!res.ok) throw new Error('Not authenticated');
            const data = await res.json();
            currentUser = data.data || data;

            if (currentUser.role !== 'admin' || (currentUser.status && currentUser.status !== 'ACTIVE')) {
                elements.unauthorizedBanner.style.display = 'block';
                elements.portalContent.style.display = 'none';
                return false;
            }

            elements.adminUserName.textContent = currentUser.name || currentUser.email;
            elements.unauthorizedBanner.style.display = 'none';
            elements.portalContent.style.display = 'grid';
            return true;
        } catch (err) {
            elements.unauthorizedBanner.style.display = 'block';
            elements.portalContent.style.display = 'none';
            return false;
        }
    }

    // Tab Navigation
    elements.tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            elements.tabs.forEach(t => t.classList.remove('active'));
            elements.views.forEach(v => v.classList.remove('active'));

            tab.classList.add('active');
            const target = tab.getAttribute('data-tab');
            document.getElementById(`view-${target}`).classList.add('active');

            if (target === 'catalog') loadCatalog();
            else if (target === 'categories') loadCategories();
            else if (target === 'vouchers') loadVouchers();
            else if (target === 'users') loadUsers();
            else if (target === 'disputes') loadDisputes();
        });
    });

    // Close Modals
    document.querySelectorAll('.btn-cancel-modal').forEach(btn => {
        btn.addEventListener('click', () => {
            elements.modalCategory.style.display = 'none';
            elements.modalVoucher.style.display = 'none';
            elements.modalUser.style.display = 'none';
            elements.modalDispute.style.display = 'none';
        });
    });

    elements.logoutBtn.addEventListener('click', () => {
        localStorage.removeItem('access_token');
        sessionStorage.removeItem('access_token');
        window.location.href = '/login';
    });

    // -----------------------------------------------------------------------
    // Catalog Moderation
    // -----------------------------------------------------------------------
    async function loadCatalog() {
        const query = elements.catalogSearch.value.trim();
        const statusVal = elements.catalogStatusFilter.value;
        let url = '/api/v1/admin/products?';
        if (query) url += `q=${encodeURIComponent(query)}&`;
        if (statusVal === 'active') url += 'is_active=true&';
        else if (statusVal === 'inactive') url += 'is_active=false&';

        try {
            const res = await fetch(url, { headers: authHeaders() });
            if (!res.ok) throw new Error('Failed to load products');
            const products = await res.json();
            renderCatalog(products);
        } catch (err) {
            elements.catalogTbody.innerHTML = '';
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 8;
            td.className = 'text-center text-danger';
            td.textContent = 'Failed to load catalog products.';
            tr.appendChild(td);
            elements.catalogTbody.appendChild(tr);
        }
    }

    function renderCatalog(products) {
        elements.catalogTbody.innerHTML = '';
        if (!products.length) {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 8;
            td.className = 'text-center text-muted';
            td.textContent = 'No products match the filter criteria.';
            tr.appendChild(td);
            elements.catalogTbody.appendChild(tr);
            return;
        }

        products.forEach(p => {
            const tr = document.createElement('tr');

            const tdCode = document.createElement('td');
            tdCode.textContent = p.code;
            tr.appendChild(tdCode);

            const tdName = document.createElement('td');
            const nameBold = document.createElement('strong');
            nameBold.textContent = p.name;
            tdName.appendChild(nameBold);
            tr.appendChild(tdName);

            const tdSeller = document.createElement('td');
            tdSeller.textContent = p.seller_name || `Seller #${p.seller_id}`;
            tr.appendChild(tdSeller);

            const tdCat = document.createElement('td');
            tdCat.textContent = p.category_name || '(None)';
            tr.appendChild(tdCat);

            const tdPrice = document.createElement('td');
            tdPrice.textContent = `${Number(p.price).toLocaleString('vi-VN')} ₫`;
            tr.appendChild(tdPrice);

            const tdStock = document.createElement('td');
            tdStock.textContent = p.stock_quantity;
            tr.appendChild(tdStock);

            const tdStatus = document.createElement('td');
            const badge = document.createElement('span');
            badge.className = p.is_active ? 'badge badge-active' : 'badge badge-inactive';
            badge.textContent = p.is_active ? 'Active' : 'Deactivated';
            tdStatus.appendChild(badge);
            tr.appendChild(tdStatus);

            const tdActions = document.createElement('td');
            const toggleBtn = document.createElement('button');
            toggleBtn.className = p.is_active ? 'btn btn-danger btn-sm' : 'btn btn-primary btn-sm';
            toggleBtn.textContent = p.is_active ? 'Deactivate' : 'Reactivate';
            toggleBtn.addEventListener('click', async () => {
                const actionWord = p.is_active ? 'deactivate' : 'reactivate';
                if (!confirm(`Are you sure you want to ${actionWord} product ${p.code} (${p.name})?`)) return;
                try {
                    const res = await fetch(`/api/v1/admin/products/${p.id}/status`, {
                        method: 'PATCH',
                        headers: {
                            'Content-Type': 'application/json',
                            ...authHeaders()
                        },
                        body: JSON.stringify({ is_active: !p.is_active })
                    });
                    if (!res.ok) throw new Error('Status change failed');
                    showAlert(`Product ${p.code} has been ${!p.is_active ? 'reactivated' : 'deactivated'}.`);
                    loadCatalog();
                } catch (err) {
                    showAlert(err.message, 'danger');
                }
            });
            tdActions.appendChild(toggleBtn);
            tr.appendChild(tdActions);

            elements.catalogTbody.appendChild(tr);
        });
    }

    elements.catalogSearch.addEventListener('input', debounce(loadCatalog, 300));
    elements.catalogStatusFilter.addEventListener('change', loadCatalog);

    // -----------------------------------------------------------------------
    // Categories Management
    // -----------------------------------------------------------------------
    async function loadCategories() {
        try {
            const res = await fetch('/api/v1/admin/categories', { headers: authHeaders() });
            if (!res.ok) throw new Error('Failed to load categories');
            categoriesList = await res.json();
            renderCategories(categoriesList);
            populateCategoryParentSelect(categoriesList);
        } catch (err) {
            elements.categoriesTbody.innerHTML = '';
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 6;
            td.className = 'text-center text-danger';
            td.textContent = 'Failed to load categories.';
            tr.appendChild(td);
            elements.categoriesTbody.appendChild(tr);
        }
    }

    function renderCategories(categories) {
        elements.categoriesTbody.innerHTML = '';
        categories.forEach(cat => {
            const tr = document.createElement('tr');

            const tdId = document.createElement('td');
            tdId.textContent = cat.id;
            tr.appendChild(tdId);

            const tdName = document.createElement('td');
            const strong = document.createElement('strong');
            strong.textContent = cat.name;
            tdName.appendChild(strong);
            tr.appendChild(tdName);

            const tdSlug = document.createElement('td');
            const codeEl = document.createElement('code');
            codeEl.textContent = cat.slug;
            tdSlug.appendChild(codeEl);
            tr.appendChild(tdSlug);

            const tdParent = document.createElement('td');
            tdParent.textContent = cat.parent_id !== null ? `#${cat.parent_id}` : '(Top level)';
            tr.appendChild(tdParent);

            const tdProducts = document.createElement('td');
            tdProducts.textContent = cat.product_count;
            tr.appendChild(tdProducts);

            const tdActions = document.createElement('td');
            const editBtn = document.createElement('button');
            editBtn.className = 'btn btn-secondary btn-sm';
            editBtn.textContent = 'Edit';
            editBtn.style.marginRight = '0.5rem';
            editBtn.addEventListener('click', () => openEditCategory(cat));

            const delBtn = document.createElement('button');
            delBtn.className = 'btn btn-danger btn-sm';
            delBtn.textContent = 'Delete';
            delBtn.addEventListener('click', async () => {
                if (!confirm(`Delete category "${cat.name}"? Subcategories will be moved to top level.`)) return;
                try {
                    const res = await fetch(`/api/v1/admin/categories/${cat.id}`, {
                        method: 'DELETE',
                        headers: authHeaders()
                    });
                    if (!res.ok) throw new Error('Failed to delete category');
                    showAlert(`Category "${cat.name}" deleted.`);
                    loadCategories();
                } catch (err) {
                    showAlert(err.message, 'danger');
                }
            });

            tdActions.appendChild(editBtn);
            tdActions.appendChild(delBtn);
            tr.appendChild(tdActions);

            elements.categoriesTbody.appendChild(tr);
        });
    }

    function populateCategoryParentSelect(categories, currentId = null) {
        elements.categoryParentSelect.innerHTML = '<option value="">(None - Top Level Category)</option>';
        categories.forEach(c => {
            if (currentId && c.id === currentId) return;
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = `${c.name} (#${c.id})`;
            elements.categoryParentSelect.appendChild(opt);
        });
    }

    function openEditCategory(cat) {
        elements.categoryTitle.textContent = 'Edit Category';
        elements.categoryIdInput.value = cat.id;
        elements.categoryNameInput.value = cat.name;
        elements.categorySlugInput.value = cat.slug;
        populateCategoryParentSelect(categoriesList, cat.id);
        elements.categoryParentSelect.value = cat.parent_id !== null ? cat.parent_id : '';
        elements.modalCategory.style.display = 'flex';
    }

    elements.btnNewCategory.addEventListener('click', () => {
        elements.categoryTitle.textContent = 'Add Category';
        elements.categoryIdInput.value = '';
        elements.categoryNameInput.value = '';
        elements.categorySlugInput.value = '';
        populateCategoryParentSelect(categoriesList);
        elements.categoryParentSelect.value = '';
        elements.modalCategory.style.display = 'flex';
    });

    elements.formCategory.addEventListener('submit', async (e) => {
        e.preventDefault();
        const id = elements.categoryIdInput.value;
        const name = elements.categoryNameInput.value.trim();
        const slug = elements.categorySlugInput.value.trim();
        const parentId = elements.categoryParentSelect.value ? parseInt(elements.categoryParentSelect.value, 10) : null;

        const payload = { name, slug, parent_id: parentId };
        const method = id ? 'PUT' : 'POST';
        const url = id ? `/api/v1/admin/categories/${id}` : '/api/v1/admin/categories';

        try {
            const res = await fetch(url, {
                method,
                headers: {
                    'Content-Type': 'application/json',
                    ...authHeaders()
                },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (!res.ok) {
                const msg = data.detail?.message || 'Category save failed';
                throw new Error(msg);
            }
            elements.modalCategory.style.display = 'none';
            showAlert(id ? 'Category updated successfully.' : 'Category created successfully.');
            loadCategories();
        } catch (err) {
            showAlert(err.message, 'danger');
        }
    });

    // -----------------------------------------------------------------------
    // Platform Vouchers
    // -----------------------------------------------------------------------
    async function loadVouchers() {
        try {
            const res = await fetch('/api/v1/admin/vouchers', { headers: authHeaders() });
            if (!res.ok) throw new Error('Failed to load vouchers');
            const vouchers = await res.json();
            renderVouchers(vouchers);
        } catch (err) {
            elements.vouchersTbody.innerHTML = '';
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 8;
            td.className = 'text-center text-danger';
            td.textContent = 'Failed to load platform vouchers.';
            tr.appendChild(td);
            elements.vouchersTbody.appendChild(tr);
        }
    }

    function renderVouchers(vouchers) {
        elements.vouchersTbody.innerHTML = '';
        if (!vouchers.length) {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 8;
            td.className = 'text-center text-muted';
            td.textContent = 'No platform vouchers found.';
            tr.appendChild(td);
            elements.vouchersTbody.appendChild(tr);
            return;
        }

        vouchers.forEach(v => {
            const tr = document.createElement('tr');

            const tdCode = document.createElement('td');
            const codeEl = document.createElement('strong');
            codeEl.textContent = v.code;
            tdCode.appendChild(codeEl);
            tr.appendChild(tdCode);

            const tdType = document.createElement('td');
            tdType.textContent = v.discount_type;
            tr.appendChild(tdType);

            const tdVal = document.createElement('td');
            if (v.discount_type === 'PERCENTAGE') {
                const pct = (v.discount_value / 100).toFixed(1);
                tdVal.textContent = `${pct}%` + (v.max_discount ? ` (Cap: ${Number(v.max_discount).toLocaleString('vi-VN')} ₫)` : '');
            } else if (v.discount_type === 'FIXED_AMOUNT') {
                tdVal.textContent = `${Number(v.discount_value).toLocaleString('vi-VN')} ₫`;
            } else {
                tdVal.textContent = 'Free Shipping';
            }
            tr.appendChild(tdVal);

            const tdMin = document.createElement('td');
            tdMin.textContent = `${Number(v.min_order_value).toLocaleString('vi-VN')} ₫`;
            tr.appendChild(tdMin);

            const tdUsage = document.createElement('td');
            tdUsage.textContent = `${v.used_count} / ${v.usage_limit !== null ? v.usage_limit : '∞'}`;
            tr.appendChild(tdUsage);

            const tdDates = document.createElement('td');
            const sDate = new Date(v.starts_at).toLocaleDateString();
            const eDate = new Date(v.ends_at).toLocaleDateString();
            tdDates.textContent = `${sDate} - ${eDate}`;
            tr.appendChild(tdDates);

            const tdStatus = document.createElement('td');
            const badge = document.createElement('span');
            badge.className = v.is_active ? 'badge badge-active' : 'badge badge-inactive';
            badge.textContent = v.is_active ? 'Active' : 'Inactive';
            tdStatus.appendChild(badge);
            tr.appendChild(tdStatus);

            const tdActions = document.createElement('td');
            const toggleBtn = document.createElement('button');
            toggleBtn.className = v.is_active ? 'btn btn-secondary btn-sm' : 'btn btn-primary btn-sm';
            toggleBtn.textContent = v.is_active ? 'Deactivate' : 'Activate';
            toggleBtn.addEventListener('click', async () => {
                try {
                    const res = await fetch(`/api/v1/admin/vouchers/${v.id}`, {
                        method: 'PATCH',
                        headers: {
                            'Content-Type': 'application/json',
                            ...authHeaders()
                        },
                        body: JSON.stringify({ is_active: !v.is_active })
                    });
                    if (!res.ok) throw new Error('Status change failed');
                    showAlert(`Voucher ${v.code} status updated.`);
                    loadVouchers();
                } catch (err) {
                    showAlert(err.message, 'danger');
                }
            });
            tdActions.appendChild(toggleBtn);
            tr.appendChild(tdActions);

            elements.vouchersTbody.appendChild(tr);
        });
    }

    elements.voucherType.addEventListener('change', () => {
        const val = elements.voucherType.value;
        if (val === 'PERCENTAGE') {
            elements.labelVoucherVal.textContent = 'Discount Value * (bps: 1000 = 10%)';
            elements.voucherVal.value = '1000';
            elements.voucherVal.min = '1';
            elements.voucherVal.max = '10000';
            document.getElementById('group-discount-val').style.display = 'block';
        } else if (val === 'FIXED_AMOUNT') {
            elements.labelVoucherVal.textContent = 'Discount Amount (VND) *';
            elements.voucherVal.value = '50000';
            elements.voucherVal.min = '1000';
            elements.voucherVal.removeAttribute('max');
            document.getElementById('group-discount-val').style.display = 'block';
        } else {
            document.getElementById('group-discount-val').style.display = 'none';
        }
    });

    elements.btnNewVoucher.addEventListener('click', () => {
        elements.formVoucher.reset();
        const now = new Date();
        const nextMonth = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
        elements.voucherStarts.value = now.toISOString().slice(0, 16);
        elements.voucherEnds.value = nextMonth.toISOString().slice(0, 16);
        elements.modalVoucher.style.display = 'flex';
    });

    elements.formVoucher.addEventListener('submit', async (e) => {
        e.preventDefault();
        const code = elements.voucherCode.value.trim().toUpperCase();
        const discountType = elements.voucherType.value;
        const discountVal = discountType === 'FREE_SHIPPING' ? 0 : parseInt(elements.voucherVal.value, 10);
        const maxDiscount = elements.voucherMax.value ? parseInt(elements.voucherMax.value, 10) : null;
        const minOrder = parseInt(elements.voucherMin.value || '0', 10);
        const usageLimit = elements.voucherUsageLimit.value ? parseInt(elements.voucherUsageLimit.value, 10) : null;
        const userLimit = elements.voucherUserLimit.value ? parseInt(elements.voucherUserLimit.value, 10) : null;
        const startsAt = new Date(elements.voucherStarts.value).toISOString();
        const endsAt = new Date(elements.voucherEnds.value).toISOString();

        const payload = {
            code,
            discount_type: discountType,
            discount_value: discountVal,
            max_discount: maxDiscount,
            min_order_value: minOrder,
            usage_limit: usageLimit,
            per_user_limit: userLimit,
            starts_at: startsAt,
            ends_at: endsAt,
            is_active: true
        };

        try {
            const res = await fetch('/api/v1/admin/vouchers', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...authHeaders()
                },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (!res.ok) {
                const msg = data.detail?.message || 'Failed to create platform voucher';
                throw new Error(msg);
            }
            elements.modalVoucher.style.display = 'none';
            showAlert(`Platform voucher ${code} created successfully.`);
            loadVouchers();
        } catch (err) {
            showAlert(err.message, 'danger');
        }
    });

    // -----------------------------------------------------------------------
    // Account Moderation
    // -----------------------------------------------------------------------
    async function loadUsers() {
        const query = elements.usersSearch.value.trim();
        const role = elements.usersRoleFilter.value;
        const statusVal = elements.usersStatusFilter.value;
        let url = '/api/v1/admin/users?';
        if (query) url += `q=${encodeURIComponent(query)}&`;
        if (role) url += `role=${encodeURIComponent(role)}&`;
        if (statusVal) url += `status=${encodeURIComponent(statusVal)}&`;

        try {
            const res = await fetch(url, { headers: authHeaders() });
            if (!res.ok) throw new Error('Failed to load users');
            const users = await res.json();
            renderUsers(users);
        } catch (err) {
            elements.usersTbody.innerHTML = '';
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 7;
            td.className = 'text-center text-danger';
            td.textContent = 'Failed to load user accounts.';
            tr.appendChild(td);
            elements.usersTbody.appendChild(tr);
        }
    }

    function renderUsers(users) {
        elements.usersTbody.innerHTML = '';
        if (!users.length) {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 7;
            td.className = 'text-center text-muted';
            td.textContent = 'No user accounts match the filter criteria.';
            tr.appendChild(td);
            elements.usersTbody.appendChild(tr);
            return;
        }

        users.forEach(u => {
            const tr = document.createElement('tr');

            const tdId = document.createElement('td');
            tdId.textContent = u.id;
            tr.appendChild(tdId);

            const tdName = document.createElement('td');
            const nameBold = document.createElement('strong');
            nameBold.textContent = u.name;
            tdName.appendChild(nameBold);
            tr.appendChild(tdName);

            const tdEmail = document.createElement('td');
            tdEmail.textContent = u.email;
            tr.appendChild(tdEmail);

            const tdRole = document.createElement('td');
            const roleBadge = document.createElement('span');
            roleBadge.className = 'badge badge-secondary';
            roleBadge.textContent = u.role.toUpperCase();
            tdRole.appendChild(roleBadge);
            tr.appendChild(tdRole);

            const tdStatus = document.createElement('td');
            const statusBadge = document.createElement('span');
            if (u.status === 'ACTIVE') statusBadge.className = 'badge badge-active';
            else if (u.status === 'RESTRICTED') statusBadge.className = 'badge badge-restricted';
            else statusBadge.className = 'badge badge-danger';
            statusBadge.textContent = u.status;
            tdStatus.appendChild(statusBadge);
            tr.appendChild(tdStatus);

            const tdDate = document.createElement('td');
            tdDate.textContent = new Date(u.created_at).toLocaleDateString();
            tr.appendChild(tdDate);

            const tdActions = document.createElement('td');
            const modBtn = document.createElement('button');
            modBtn.className = 'btn btn-secondary btn-sm';
            modBtn.textContent = 'Moderate';
            modBtn.addEventListener('click', () => openUserModeration(u));
            tdActions.appendChild(modBtn);
            tr.appendChild(tdActions);

            elements.usersTbody.appendChild(tr);
        });
    }

    elements.usersSearch.addEventListener('input', debounce(loadUsers, 300));
    elements.usersRoleFilter.addEventListener('change', loadUsers);
    elements.usersStatusFilter.addEventListener('change', loadUsers);

    function openUserModeration(u) {
        elements.userStatusId.value = u.id;
        elements.userStatusDesc.textContent = `${u.name} (${u.email}) - Role: ${u.role}`;
        elements.userStatusSelect.value = u.status;
        elements.userStatusReason.value = '';

        elements.userAuditsList.innerHTML = '<strong>Recent Status History:</strong><br>';
        if (u.recent_audits && u.recent_audits.length) {
            u.recent_audits.forEach(a => {
                const item = document.createElement('div');
                item.style.padding = '0.25rem 0';
                item.textContent = `${new Date(a.created_at).toLocaleDateString()}: ${a.old_status} ➔ ${a.new_status} (Reason: ${a.reason || 'N/A'})`;
                elements.userAuditsList.appendChild(item);
            });
        } else {
            elements.userAuditsList.innerHTML += '<em>No previous status changes recorded.</em>';
        }

        elements.modalUser.style.display = 'flex';
    }

    elements.formUserStatus.addEventListener('submit', async (e) => {
        e.preventDefault();
        const userId = elements.userStatusId.value;
        const statusVal = elements.userStatusSelect.value;
        const reason = elements.userStatusReason.value.trim();

        try {
            const res = await fetch(`/api/v1/admin/users/${userId}/status`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    ...authHeaders()
                },
                body: JSON.stringify({ status: statusVal, reason })
            });
            const data = await res.json();
            if (!res.ok) {
                const msg = data.detail?.message || 'Status change failed';
                throw new Error(msg);
            }
            elements.modalUser.style.display = 'none';
            showAlert('User account status updated successfully.');
            loadUsers();
        } catch (err) {
            showAlert(err.message, 'danger');
        }
    });

    // -----------------------------------------------------------------------
    // Dispute Adjudication
    // -----------------------------------------------------------------------
    async function loadDisputes() {
        const filterVal = elements.disputesFilterStatus.value;
        let url = '/api/v1/admin/disputes?';
        if (filterVal) url += `status=${encodeURIComponent(filterVal)}`;

        try {
            const res = await fetch(url, { headers: authHeaders() });
            if (!res.ok) throw new Error('Failed to load disputes');
            const disputes = await res.json();
            renderDisputes(disputes);
        } catch (err) {
            elements.disputesTbody.innerHTML = '';
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 8;
            td.className = 'text-center text-danger';
            td.textContent = 'Failed to load disputes.';
            tr.appendChild(td);
            elements.disputesTbody.appendChild(tr);
        }
    }

    function renderDisputes(disputes) {
        elements.disputesTbody.innerHTML = '';
        if (!disputes.length) {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 8;
            td.className = 'text-center text-muted';
            td.textContent = 'No return/refund disputes found.';
            tr.appendChild(td);
            elements.disputesTbody.appendChild(tr);
            return;
        }

        disputes.forEach(d => {
            const tr = document.createElement('tr');

            const tdId = document.createElement('td');
            tdId.textContent = `#${d.id}`;
            tr.appendChild(tdId);

            const tdOrder = document.createElement('td');
            tdOrder.textContent = `Order #${d.order_id} (Sub #${d.seller_order_id})`;
            tr.appendChild(tdOrder);

            const tdBuyer = document.createElement('td');
            tdBuyer.textContent = d.buyer_name || `Buyer #${d.buyer_id}`;
            tr.appendChild(tdBuyer);

            const tdSeller = document.createElement('td');
            tdSeller.textContent = d.seller_name || `Seller #${d.seller_id}`;
            tr.appendChild(tdSeller);

            const tdReason = document.createElement('td');
            const reasonStrong = document.createElement('div');
            reasonStrong.textContent = d.reason;
            tdReason.appendChild(reasonStrong);
            if (d.evidence) {
                const evSmall = document.createElement('small');
                evSmall.className = 'text-muted';
                evSmall.textContent = `Evidence: ${d.evidence}`;
                tdReason.appendChild(evSmall);
            }
            tr.appendChild(tdReason);

            const tdStatus = document.createElement('td');
            const badge = document.createElement('span');
            if (d.status === 'APPROVED') badge.className = 'badge badge-success';
            else if (d.status === 'REJECTED') badge.className = 'badge badge-danger';
            else badge.className = 'badge badge-warning';
            badge.textContent = d.status;
            tdStatus.appendChild(badge);
            tr.appendChild(tdStatus);

            const tdDecider = document.createElement('td');
            tdDecider.textContent = d.decided_by_name ? `${d.decided_by_name} (${new Date(d.decided_at).toLocaleDateString()})` : '—';
            tr.appendChild(tdDecider);

            const tdActions = document.createElement('td');
            if (d.status === 'PENDING') {
                const decideBtn = document.createElement('button');
                decideBtn.className = 'btn btn-primary btn-sm';
                decideBtn.textContent = 'Adjudicate';
                decideBtn.addEventListener('click', () => openDisputeModal(d));
                tdActions.appendChild(decideBtn);
            } else {
                const viewBtn = document.createElement('button');
                viewBtn.className = 'btn btn-secondary btn-sm';
                viewBtn.textContent = 'View Notes';
                viewBtn.addEventListener('click', () => {
                    alert(`Dispute #${d.id} Resolution:\nAction: ${d.status}\nDecided by: ${d.decided_by_name || 'Admin'}\nNotes: ${d.decision_notes || 'None'}`);
                });
                tdActions.appendChild(viewBtn);
            }
            tr.appendChild(tdActions);

            elements.disputesTbody.appendChild(tr);
        });
    }

    elements.disputesFilterStatus.addEventListener('change', loadDisputes);

    function openDisputeModal(d) {
        elements.disputeDecisionId.value = d.id;
        elements.disputeModalSummary.innerHTML = `
            <strong>Dispute #${d.id} for Order #${d.order_id} (Sub-order #${d.seller_order_id})</strong><br>
            <span>Buyer: ${escapeHtml(d.buyer_name || 'Buyer')} | Seller: ${escapeHtml(d.seller_name || 'Seller')}</span><br>
            <span>Reason: ${escapeHtml(d.reason)}</span><br>
            <span>Evidence: ${escapeHtml(d.evidence || 'None provided')}</span>
        `;
        elements.disputeAction.value = 'APPROVE';
        elements.groupDisputeRestock.style.display = 'block';
        elements.disputeRestock.checked = true;
        elements.disputeNotes.value = '';
        elements.modalDispute.style.display = 'flex';
    }

    elements.disputeAction.addEventListener('change', () => {
        if (elements.disputeAction.value === 'APPROVE') {
            elements.groupDisputeRestock.style.display = 'block';
        } else {
            elements.groupDisputeRestock.style.display = 'none';
        }
    });

    elements.formDisputeDecision.addEventListener('submit', async (e) => {
        e.preventDefault();
        const disputeId = elements.disputeDecisionId.value;
        const action = elements.disputeAction.value;
        const isRestockable = action === 'APPROVE' ? elements.disputeRestock.checked : false;
        const decisionNotes = elements.disputeNotes.value.trim();

        try {
            const res = await fetch(`/api/v1/admin/disputes/${disputeId}/decision`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...authHeaders()
                },
                body: JSON.stringify({
                    action,
                    is_restockable: isRestockable,
                    decision_notes: decisionNotes
                })
            });
            const data = await res.json();
            if (!res.ok) {
                const msg = data.detail?.message || 'Failed to submit adjudication decision';
                throw new Error(msg);
            }
            elements.modalDispute.style.display = 'none';
            showAlert(`Dispute #${disputeId} has been ${action === 'APPROVE' ? 'approved' : 'rejected'}.`);
            loadDisputes();
        } catch (err) {
            showAlert(err.message, 'danger');
        }
    });

    function debounce(func, wait) {
        let timeout;
        return function(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // Initialize
    const isAuthed = await checkAuth();
    if (isAuthed) {
        loadCatalog();
    }
});
