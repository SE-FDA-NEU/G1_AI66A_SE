/* Admin Portal JavaScript Controller */

document.addEventListener('DOMContentLoaded', async () => {
    let currentUser = null;
    let categoriesList = [];
    let pageToken = null;
    let mutating = false;
    let activeModal = null;
    let modalOpener = null;
    const listVersions = new Map();

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
        const errorBox = document.getElementById('admin-error');
        elements.alertBox.textContent = type === 'danger' ? '' : message;
        errorBox.textContent = type === 'danger' ? message : '';
        if (type === 'danger' && activeModal) {
            const feedback = formFeedback(activeModal.querySelector('form'));
            feedback.textContent = message;
            if (!mutating) feedback.focus();
        }
    }

    function formFeedback(form) {
        let feedback = form.querySelector('.form-feedback');
        if (!feedback) {
            feedback = document.createElement('p');
            feedback.className = 'form-feedback';
            feedback.tabIndex = -1;
            feedback.setAttribute('role', 'alert');
            form.prepend(feedback);
        }
        return feedback;
    }

    function formProgress(form) {
        let status = form.querySelector('.form-progress');
        if (!status) {
            status = document.createElement('p');
            status.className = 'form-progress';
            status.setAttribute('role', 'status');
            status.setAttribute('aria-live', 'polite');
            form.prepend(status);
        }
        return status;
    }

    function openModal(modal) {
        if (mutating) return;
        modalOpener = document.activeElement;
        activeModal = modal;
        const heading = modal.querySelector('h3');
        heading.id ||= `${modal.id}-heading`;
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-labelledby', heading.id);
        modal.querySelectorAll('input,select,textarea').forEach(input => input.setCustomValidity(''));
        formFeedback(modal.querySelector('form')).textContent = '';
        formProgress(modal.querySelector('form')).textContent = '';
        modal.style.display = 'flex';
        document.querySelector('main').inert = true;
        document.querySelector('header').inert = true;
        modal.querySelector('input:not([type="hidden"]),select,textarea,button').focus();
    }

    function closeModal(force = false, modal = activeModal) {
        if (!activeModal || activeModal !== modal || (mutating && !force)) return;
        activeModal.style.display = 'none';
        activeModal = null;
        document.querySelector('main').inert = false;
        document.querySelector('header').inert = false;
        if (modalOpener?.isConnected && !modalOpener.disabled) modalOpener.focus();
    }

    document.addEventListener('keydown', event => {
        if (!activeModal) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            closeModal();
        } else if (event.key === 'Tab') {
            const controls = [...activeModal.querySelectorAll('input,select,textarea,button,a[href]')]
                .filter(control => !control.disabled && control.getClientRects().length);
            if (!controls.length) { event.preventDefault(); return; }
            const first = controls[0], last = controls.at(-1);
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault(); last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault(); first.focus();
            }
        }
    });

    for (const form of [elements.formCategory, elements.formVoucher]) {
        const clearValidation = () => {
            form.querySelectorAll('input,select').forEach(input => input.setCustomValidity(''));
            formFeedback(form).textContent = '';
        };
        form.addEventListener('input', clearValidation);
        form.addEventListener('change', clearValidation);
    }

    function requireAccountContext() {
        if (getToken() === pageToken) return;
        closeModal(true);
        elements.portalContent.style.display = 'none';
        elements.unauthorizedBanner.style.display = 'block';
        for (const body of [elements.catalogTbody, elements.categoriesTbody, elements.vouchersTbody]) body.replaceChildren();
        const error = new Error('Your account changed. Sign in again and reload the portal.');
        error.accountChanged = true;
        throw error;
    }

    async function adminRequest(url, options = {}) {
        requireAccountContext();
        const response = await fetch(url, {...options, headers: {
            'Content-Type': 'application/json', ...authHeaders(), ...options.headers,
        }});
        const data = response.status === 204 ? null : await response.json();
        requireAccountContext();
        if (!response.ok) {
            const detail = data?.error || data?.detail;
            const error = new Error(detail?.message || 'The request failed. Review your input and try again.');
            if (response.status === 401 || ['ERR_ADMIN_REQUIRED', 'ERR_ACCOUNT_RESTRICTED'].includes(detail?.code)) {
                closeModal(true);
                elements.portalContent.style.display = 'none';
                elements.unauthorizedBanner.style.display = 'block';
                error.accountChanged = true;
            }
            throw error;
        }
        return data;
    }

    async function runChange(button, form, action, focusAfter) {
        if (mutating) return;
        mutating = true;
        const controls = [...document.querySelectorAll('#admin-portal-content input, #admin-portal-content select, #admin-portal-content button'),
            ...(activeModal?.querySelectorAll('input,select,textarea,button') || [])];
        const previous = controls.map(control => [control, control.disabled]);
        controls.forEach(control => {control.disabled = true;});
        (form || button).setAttribute('aria-busy', 'true');
        if (form) {
            formFeedback(form).textContent = '';
            formProgress(form).textContent = 'Saving changes...';
        }
        showAlert('Saving changes...');
        let succeeded = false, failed = false;
        try { await action(); succeeded = true; }
        catch (error) {
            if (!error.accountChanged) {
                const message = `${error.message} Your input is preserved. Review the current data before retrying.`;
                showAlert(message, 'danger');
                failed = true;
            }
        } finally {
            previous.forEach(([control, disabled]) => {control.disabled = disabled;});
            (form || button).setAttribute('aria-busy', 'false');
            if (form) formProgress(form).textContent = '';
            mutating = false;
        }
        if (failed && form) formFeedback(form).focus();
        if (succeeded && focusAfter) focusAfter().focus();
    }

    function listState(kind, body, columns, message, retry) {
        document.getElementById(`${kind}-feedback`).textContent = message;
        body.replaceChildren();
        const row = document.createElement('tr'), cell = document.createElement('td');
        cell.colSpan = columns;
        cell.textContent = message;
        if (retry) {
            const button = document.createElement('button');
            button.type = 'button'; button.textContent = 'Retry'; button.className = 'button button--secondary';
            button.addEventListener('click', retry); cell.append(' ', button);
        }
        row.append(cell); body.append(row);
    }

    async function loadRows(kind, url, body, columns, render, retry) {
        const version = (listVersions.get(kind) || 0) + 1;
        listVersions.set(kind, version);
        body.setAttribute('aria-busy', 'true');
        listState(kind, body, columns, 'Loading...', null);
        try {
            const rows = await adminRequest(url);
            if (listVersions.get(kind) !== version) return;
            if (!Array.isArray(rows)) throw new Error('Unexpected server response.');
            render(rows);
            if (!rows.length) listState(kind, body, columns, 'No matching records.', null);
            document.getElementById(`${kind}-feedback`).textContent =
                `${rows.length} record${rows.length === 1 ? '' : 's'} loaded.`;
        } catch (error) {
            if (!error.accountChanged && listVersions.get(kind) === version) {
                listState(kind, body, columns, `Could not load records. ${error.message}`, retry);
            }
        } finally {
            if (listVersions.get(kind) === version) body.setAttribute('aria-busy', 'false');
        }
    }

    // Check Admin Authentication
    async function checkAuth() {
        const token = getToken();
        pageToken = token;
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
    document.querySelectorAll('[data-cancel-modal]').forEach(btn => {
        btn.addEventListener('click', () => {
            closeModal();
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
        const params = new URLSearchParams();
        const query = elements.catalogSearch.value.trim();
        const status = elements.catalogStatusFilter.value;
        if (query) params.set('q', query);
        if (status) params.set('is_active', String(status === 'active'));
        return loadRows('catalog', `/api/v1/admin/products?${params}`, elements.catalogTbody,
            8, renderCatalog, loadCatalog);
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
            toggleBtn.className = p.is_active ? 'button button--danger button--sm' : 'button button--sm';
            toggleBtn.textContent = p.is_active ? 'Deactivate' : 'Reactivate';
            toggleBtn.id = `catalog-toggle-${p.id}`;
            toggleBtn.setAttribute('aria-label', `${p.is_active ? 'Deactivate' : 'Reactivate'} product ${p.code}`);
            toggleBtn.addEventListener('click', async () => {
                if (mutating) return;
                const action = p.is_active ? 'deactivate' : 'reactivate';
                if (!confirm(`Confirm: ${action} product ${p.code} (${p.name})?`)) return;
                return runChange(toggleBtn, null, async () => {
                    await adminRequest(`/api/v1/admin/products/${p.id}/status`,
                        {method: 'PATCH', body: JSON.stringify({is_active: !p.is_active})});
                    await loadCatalog();
                    showAlert(`Product ${p.code} has been ${p.is_active ? 'deactivated' : 'reactivated'}.`);
                }, () => document.getElementById(`catalog-toggle-${p.id}`) || elements.catalogSearch);
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
        return loadRows('categories', '/api/v1/admin/categories', elements.categoriesTbody, 6,
            rows => {categoriesList = rows; renderCategories(rows); populateCategoryParentSelect(rows);},
            loadCategories);
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
            editBtn.className = 'button button--secondary button--sm';
            editBtn.textContent = 'Edit';
            editBtn.style.marginRight = '0.5rem';
            editBtn.addEventListener('click', () => openEditCategory(cat));

            const delBtn = document.createElement('button');
            delBtn.className = 'button button--danger button--sm';
            delBtn.textContent = 'Delete';
            editBtn.setAttribute('aria-label', `Edit category ${cat.name}`);
            delBtn.setAttribute('aria-label', `Delete category ${cat.name}`);
            delBtn.addEventListener('click', async () => {
                if (mutating) return;
                const parent = cat.parent_id === null ? 'the top level' : `parent category #${cat.parent_id}`;
                if (!confirm(`Delete category "${cat.name}"? Direct children will move to ${parent}; products will be unlinked.`)) return;
                return runChange(delBtn, null, async () => {
                    await adminRequest(`/api/v1/admin/categories/${cat.id}`, {method: 'DELETE'});
                    await loadCategories();
                    showAlert(`Category "${cat.name}" deleted.`);
                }, () => elements.btnNewCategory);
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
        openModal(elements.modalCategory);
    }

    elements.btnNewCategory.addEventListener('click', () => {
        elements.categoryTitle.textContent = 'Add Category';
        elements.categoryIdInput.value = '';
        elements.categoryNameInput.value = '';
        elements.categorySlugInput.value = '';
        populateCategoryParentSelect(categoriesList);
        elements.categoryParentSelect.value = '';
        openModal(elements.modalCategory);
    });

    elements.formCategory.addEventListener('submit', async event => {
        event.preventDefault();
        if (mutating) return;
        elements.categoryNameInput.value = elements.categoryNameInput.value.trim();
        elements.categorySlugInput.value = elements.categorySlugInput.value.trim();
        if (!elements.formCategory.reportValidity()) return;
        const id = elements.categoryIdInput.value;
        const payload = {name: elements.categoryNameInput.value, slug: elements.categorySlugInput.value,
            parent_id: elements.categoryParentSelect.value ? Number(elements.categoryParentSelect.value) : null};
        return runChange(event.submitter, elements.formCategory, async () => {
            await adminRequest(id ? `/api/v1/admin/categories/${id}` : '/api/v1/admin/categories',
                {method: id ? 'PUT' : 'POST', body: JSON.stringify(payload)});
            closeModal(true);
            await loadCategories();
            showAlert(id ? 'Category updated successfully.' : 'Category created successfully.');
        }, () => elements.btnNewCategory);
    });

    // -----------------------------------------------------------------------
    // Platform Vouchers
    // -----------------------------------------------------------------------
    async function loadVouchers() {
        return loadRows('vouchers', '/api/v1/admin/vouchers', elements.vouchersTbody,
            9, renderVouchers, loadVouchers);
    }

    function voucherDate(value) {
        const timestamp = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : value + 'Z';
        const date = new Date(timestamp);
        return Number.isFinite(date.getTime()) ? date.toLocaleString('en-GB', {
            timeZone: 'UTC', dateStyle: 'medium', timeStyle: 'short',
        }) + ' UTC' : 'Date unavailable';
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
            const sDate = voucherDate(v.starts_at);
            const eDate = voucherDate(v.ends_at);
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
            toggleBtn.className = v.is_active ? 'button button--secondary button--sm' : 'button button--sm';
            toggleBtn.textContent = v.is_active ? 'Deactivate' : 'Activate';
            toggleBtn.id = `voucher-toggle-${v.id}`;
            toggleBtn.setAttribute('aria-label', `${v.is_active ? 'Deactivate' : 'Activate'} voucher ${v.code}`);
            toggleBtn.addEventListener('click', async () => {
                if (mutating) return;
                if (!confirm(`${v.is_active ? 'Deactivate' : 'Activate'} platform voucher ${v.code}?`)) return;
                return runChange(toggleBtn, null, async () => {
                    await adminRequest(`/api/v1/admin/vouchers/${v.id}`,
                        {method: 'PATCH', body: JSON.stringify({is_active: !v.is_active})});
                    await loadVouchers();
                    showAlert(`Voucher ${v.code} status updated.`);
                }, () => document.getElementById(`voucher-toggle-${v.id}`) || elements.btnNewVoucher);
            });
            tdActions.appendChild(toggleBtn);
            tr.appendChild(tdActions);

            elements.vouchersTbody.appendChild(tr);
        });
    }

    function updateVoucherType() {
        const val = elements.voucherType.value;
        elements.voucherVal.disabled = val === 'FREE_SHIPPING';
        elements.voucherMax.disabled = val === 'FIXED_AMOUNT';
        elements.voucherMax.closest('.form-group').style.display =
            val === 'FIXED_AMOUNT' ? 'none' : 'flex';
        if (val === 'PERCENTAGE') {
            elements.labelVoucherVal.textContent = 'Discount Value * (bps: 1000 = 10%)';
            elements.voucherVal.value = '1000';
            elements.voucherVal.min = '1';
            elements.voucherVal.max = '10000';
            document.getElementById('group-discount-val').style.display = 'block';
        } else if (val === 'FIXED_AMOUNT') {
            elements.labelVoucherVal.textContent = 'Discount Amount (VND) *';
            elements.voucherVal.value = '50000';
            elements.voucherVal.min = '1';
            elements.voucherVal.removeAttribute('max');
            document.getElementById('group-discount-val').style.display = 'block';
        } else {
            document.getElementById('group-discount-val').style.display = 'none';
        }
    }
    elements.voucherType.addEventListener('change', updateVoucherType);

    elements.btnNewVoucher.addEventListener('click', () => {
        elements.formVoucher.reset();
        updateVoucherType();
        const now = new Date();
        const nextMonth = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
        elements.voucherStarts.value = now.toISOString().slice(0, 16);
        elements.voucherEnds.value = nextMonth.toISOString().slice(0, 16);
        openModal(elements.modalVoucher);
    });

    elements.formVoucher.addEventListener('submit', async event => {
        event.preventDefault();
        if (mutating) return;
        elements.voucherCode.value = elements.voucherCode.value.trim().toUpperCase();
        const numericFields = [elements.voucherVal, elements.voucherMax, elements.voucherMin,
            elements.voucherUsageLimit, elements.voucherUserLimit];
        for (const field of numericFields) {
            field.setCustomValidity(!field.disabled && field.value !== '' &&
                !Number.isSafeInteger(Number(field.value)) ? 'Enter a whole number.' : '');
        }
        const starts = new Date(elements.voucherStarts.value + 'Z');
        const ends = new Date(elements.voucherEnds.value + 'Z');
        elements.voucherEnds.setCustomValidity(Number.isFinite(starts.getTime()) &&
            Number.isFinite(ends.getTime()) && ends > starts ? '' : 'End date must be after the start date (UTC).');
        if (!elements.formVoucher.reportValidity()) return;
        const discountType = elements.voucherType.value;
        const payload = {
            code: elements.voucherCode.value, discount_type: discountType,
            discount_value: discountType === 'FREE_SHIPPING' ? 0 : Number(elements.voucherVal.value),
            min_order_value: Number(elements.voucherMin.value || 0),
            usage_limit: elements.voucherUsageLimit.value === '' ? null : Number(elements.voucherUsageLimit.value),
            per_user_limit: elements.voucherUserLimit.value === '' ? null : Number(elements.voucherUserLimit.value),
            starts_at: starts.toISOString(), ends_at: ends.toISOString(), is_active: true,
        };
        if (!elements.voucherMax.disabled) {
            payload.max_discount = elements.voucherMax.value === '' ? null : Number(elements.voucherMax.value);
        }
        const discount = discountType === 'PERCENTAGE' ? `${payload.discount_value / 100}% off` :
            discountType === 'FREE_SHIPPING' ? 'free shipping' : `${payload.discount_value} VND off`;
        if (!confirm(`Create active platform voucher ${payload.code}: ${discount}, from ${payload.starts_at} to ${payload.ends_at} (UTC)?`)) return;
        return runChange(event.submitter, elements.formVoucher, async () => {
            await adminRequest('/api/v1/admin/vouchers', {method: 'POST', body: JSON.stringify(payload)});
            closeModal(true);
            await loadVouchers();
            showAlert(`Platform voucher ${payload.code} created successfully.`);
        }, () => elements.btnNewVoucher);
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

        elements.usersTbody.setAttribute('aria-busy', 'true');
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
        } finally {
            elements.usersTbody.setAttribute('aria-busy', 'false');
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
            modBtn.className = 'button button--secondary button--sm';
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

        openModal(elements.modalUser);
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
            closeModal(true, elements.modalUser);
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

        elements.disputesTbody.setAttribute('aria-busy', 'true');
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
        } finally {
            elements.disputesTbody.setAttribute('aria-busy', 'false');
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
                decideBtn.className = 'button button--sm';
                decideBtn.textContent = 'Adjudicate';
                decideBtn.addEventListener('click', () => openDisputeModal(d));
                tdActions.appendChild(decideBtn);
            } else {
                const viewBtn = document.createElement('button');
                viewBtn.className = 'button button--secondary button--sm';
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
        openModal(elements.modalDispute);
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
            closeModal(true, elements.modalDispute);
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
