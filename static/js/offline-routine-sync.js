/**
 * BCET Hub - Offline & Instant LocalStorage Routine + Notice Synchronization Script
 * Supports offline storage, 0ms instant loading, background version checks,
 * offline filter dropdown updates, and instant re-rendering when Admin updates Routine CSV or Notices.
 */

(function () {
    const STORAGE_ROUTINE_KEY = 'bcet_routine_data_v2';
    const STORAGE_ROUTINE_VER_KEY = 'bcet_routine_version_v2';
    const STORAGE_NOTICES_KEY = 'bcet_notices_data_v2';
    const STORAGE_NOTICES_VER_KEY = 'bcet_notice_version_v2';

    const PREF_YEAR_KEY = 'bcet_user_pref_year';
    const PREF_SEC_KEY = 'bcet_user_pref_sec';
    const PREF_DAY_KEY = 'bcet_user_pref_day';

    const DAYS_ORDER = { 'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6 };
    const DAY_NAMES = { 'MON': 'Monday', 'TUE': 'Tuesday', 'WED': 'Wednesday', 'THU': 'Thursday', 'FRI': 'Friday', 'SAT': 'Saturday', 'SUN': 'Sunday' };

    function getTodayDayCode() {
        const jsDay = new Date().getDay();
        const map = { 0: 'SUN', 1: 'MON', 2: 'TUE', 3: 'WED', 4: 'THU', 5: 'FRI', 6: 'SAT' };
        return map[jsDay] || 'MON';
    }

    function getCurrentTimeMins() {
        const now = new Date();
        return now.getHours() * 60 + now.getMinutes();
    }

    function parseTimeToMins(timeStr) {
        if (!timeStr) return 0;
        const parts = timeStr.trim().split(':');
        const h = parseInt(parts[0], 10) || 0;
        const m = parseInt(parts[1], 10) || 0;
        return h * 60 + m;
    }

    function formatTime12(timeStr) {
        if (!timeStr) return '';
        const parts = timeStr.trim().split(':');
        let h = parseInt(parts[0], 10) || 0;
        const m = parseInt(parts[1], 10) || 0;
        const ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12;
        if (h === 0) h = 12;
        const mStr = m < 10 ? '0' + m : m;
        return `${h}:${mStr} ${ampm}`;
    }

    function calculateSlotStatus(slot, targetDay, todayDayCode) {
        const tIdx = DAYS_ORDER[targetDay] !== undefined ? DAYS_ORDER[targetDay] : 0;
        const cIdx = DAYS_ORDER[todayDayCode] !== undefined ? DAYS_ORDER[todayDayCode] : 0;

        if (tIdx < cIdx) return 'PAST';
        if (tIdx > cIdx) return 'UPCOMING';

        const nowMins = getCurrentTimeMins();
        const startMins = parseTimeToMins(slot.start_time);
        const endMins = parseTimeToMins(slot.end_time);

        if (nowMins < startMins) return 'UPCOMING';
        if (nowMins >= startMins && nowMins <= endMins) return 'LIVE';
        return 'PAST';
    }

    function renderNoticeBanner(notices) {
        const wrapper = document.getElementById('global-notice-wrapper');
        if (!wrapper) return;

        if (!notices || notices.length === 0) {
            wrapper.innerHTML = '';
            return;
        }

        let html = '';
        notices.forEach(n => {
            const iconName = n.icon || 'bell';
            const urlIcon = n.n_url_icon || 'external-link';
            const urlName = n.n_url_name || 'View Detail';
            
            html += `
            <div class="notice-banner">
                <div class="banner-left">
                    <div class="banner-icon">
                        <i data-lucide="${iconName}" style="width: 18px; height: 18px;"></i>
                    </div>
                    <div class="banner-text">
                        <p>${n.notice || ''}</p>
                    </div>
                </div>
                ${n.n_url ? `
                    <a href="${n.n_url}" target="_blank" rel="noopener" class="icon-btn">
                        <i data-lucide="${urlIcon}" style="width: 14px; height: 14px;"></i> ${urlName}
                    </a>
                ` : ''}
            </div>`;
        });

        wrapper.innerHTML = html;
        if (window.lucide) window.lucide.createIcons();
    }

    function syncSelectOptions(allSlots) {
        if (!allSlots || !allSlots.length) return;
        const sections = Array.from(new Set(allSlots.map(s => (s.section || '').trim()).filter(Boolean)));
        const years = Array.from(new Set(allSlots.map(s => String(s.year || '').trim()).filter(Boolean))).sort();

        const secSelects = document.querySelectorAll('#sec, #sec-select');
        secSelects.forEach(sel => {
            const existingValues = Array.from(sel.options).map(opt => opt.value.toLowerCase());
            sections.forEach(secName => {
                if (!existingValues.includes(secName.toLowerCase())) {
                    const opt = document.createElement('option');
                    opt.value = secName;
                    opt.textContent = secName;
                    sel.appendChild(opt);
                }
            });
        });

        const yrSelects = document.querySelectorAll('#year, #yr-select');
        yrSelects.forEach(sel => {
            const existingValues = Array.from(sel.options).map(opt => opt.value);
            years.forEach(yrName => {
                if (!existingValues.includes(yrName)) {
                    const opt = document.createElement('option');
                    opt.value = yrName;
                    opt.textContent = yrName === '1' ? '1st Year' : yrName === '2' ? '2nd Year' : yrName === '3' ? '3rd Year' : `${yrName}th Year`;
                    sel.appendChild(opt);
                }
            });
        });
    }

    function renderRoutineTable(allSlots, yearFilter, secFilter, dayFilter) {
        const cardBody = document.querySelector('.routine-card-body') || 
                         document.querySelector('.routine-section .card-body');

        if (!cardBody || cardBody.closest('.lunch-highlight-card') || cardBody.closest('.induction-highlight-card')) return;

        const isHomePage = document.querySelector('.routine-section') !== null;
        const todayDayCode = getTodayDayCode();

        // On Home Page, ALWAYS show Today's Live Routine, NOT selected day from routine page
        if (isHomePage) {
            dayFilter = todayDayCode;
        } else {
            dayFilter = String(dayFilter || todayDayCode).trim().toUpperCase();
        }

        // save holiday html
        if (cardBody.querySelector('.holiday-state')) {
            window._cachedHolidayHTML = cardBody.innerHTML;
        }

        // check holiday
        if (isHomePage || dayFilter === todayDayCode) {
            if (cardBody.querySelector('.holiday-state')) {
                return;
            }
            if (window._cachedHolidayHTML) {
                cardBody.innerHTML = window._cachedHolidayHTML;
                if (window.lucide) window.lucide.createIcons();
                return;
            }
        }

        yearFilter = String(yearFilter || '1').trim();
        secFilter = (secFilter || 'CSE - A').trim().toLowerCase();

        // Ensure dropdown options match available routine sections/years
        syncSelectOptions(allSlots);

        // Save selected filter in localStorage
        localStorage.setItem(PREF_YEAR_KEY, yearFilter);
        localStorage.setItem(PREF_SEC_KEY, secFilter);
        if (!isHomePage) {
            localStorage.setItem(PREF_DAY_KEY, dayFilter);
        }

        const filtered = allSlots.filter(s => {
            const matchYear = !yearFilter || String(s.year).trim() === yearFilter;
            const matchSec = !secFilter || String(s.section).trim().toLowerCase() === secFilter;
            const matchDay = !dayFilter || String(s.day).trim().toUpperCase() === dayFilter;
            return matchYear && matchSec && matchDay;
        });

        filtered.sort((a, b) => (parseInt(a.slot_number, 10) || 0) - (parseInt(b.slot_number, 10) || 0));

        // Update headers based on page type
        if (isHomePage) {
            const homeHeader = document.querySelector('.routine-section .routine-header h3');
            if (homeHeader) homeHeader.textContent = "Today's Class Routine & Live Tracker";
            const homeDayTag = document.querySelector('.routine-section .routine-header .day-tag');
            if (homeDayTag) homeDayTag.textContent = `${DAY_NAMES[todayDayCode] || todayDayCode} Routine`;
        } else {
            const pageHeader = document.querySelector('.page-wrapper .dash-card .header-left h3');
            if (pageHeader && !pageHeader.closest('.lunch-highlight-card')) {
                pageHeader.textContent = `${yearFilter} Year - Section ${secFilter.toUpperCase()} Schedule`;
            }
            const pageDayTag = document.querySelector('.page-wrapper .dash-card .header-left .day-tag');
            if (pageDayTag && !pageDayTag.closest('.lunch-highlight-card')) {
                pageDayTag.textContent = DAY_NAMES[dayFilter] ? `${DAY_NAMES[dayFilter]} Routine` : dayFilter;
            }
        }

        if (filtered.length === 0) {
            cardBody.innerHTML = `<p class="empty-state">No routine classes scheduled for ${secFilter.toUpperCase()} on ${DAY_NAMES[dayFilter] || dayFilter}.</p>`;
            return;
        }

        let tableHtml = `
        <div class="routine-table-responsive">
            <table class="routine-table">
                <thead>
                    <tr>
                        <th>Slot</th>
                        <th>Time</th>
                        <th>Subject Code</th>
                        <th>Subject Title</th>
                        <th>Faculty</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>`;

        filtered.forEach(s => {
            const status = calculateSlotStatus(s, dayFilter, todayDayCode);
            const facCode = (s.faculty_code || '').trim();
            const facDisplay = (!facCode || facCode === '--') ? '--' : facCode;
            const facLink = (facDisplay !== '--') ? `/search?q=${encodeURIComponent(facDisplay)}` : null;

            let badgeContent = '';
            if (status === 'LIVE') {
                badgeContent = `<span class="pulse-dot"></span> LIVE NOW`;
            } else if (status === 'UPCOMING') {
                badgeContent = `<i data-lucide="clock"></i> UPCOMING`;
            } else {
                badgeContent = `<i data-lucide="check-circle"></i> COMPLETED`;
            }

            tableHtml += `
            <tr class="slot-row status-row-${status.toLowerCase()}">
                <td><span class="slot-num-pill">Slot ${s.slot_number}</span></td>
                <td class="time-cell">${formatTime12(s.start_time)} - ${formatTime12(s.end_time)}</td>
                <td><span class="code-badge">${s.subject_code || ''}</span></td>
                <td class="sub-name-cell">${s.subject_name || ''}</td>
                <td class="fac-cell">
                    ${facLink ? `<a href="${facLink}" class="fac-link"><i data-lucide="user-check"></i> ${facDisplay}</a>` : `<span class="fac-code-raw">${facDisplay}</span>`}
                </td>
                <td>
                    <span class="status-badge badge-${status.toLowerCase()}">
                        ${badgeContent}
                    </span>
                </td>
            </tr>`;
        });

        tableHtml += `</tbody></table></div>`;

        cardBody.innerHTML = tableHtml;
        if (window.lucide) window.lucide.createIcons();
    }

    function setupFilterChangeHandlers() {
        const filterForms = document.querySelectorAll('.routine-filter-form, .sec-select-form');
        const filterSelects = document.querySelectorAll('#year, #sec, #day, #yr-select, #sec-select');

        function updateFromSelects(e) {
            const yearElem = document.getElementById('year') || document.getElementById('yr-select');
            const secElem = document.getElementById('sec') || document.getElementById('sec-select');
            const dayElem = document.getElementById('day');

            const curYear = yearElem ? yearElem.value : (localStorage.getItem(PREF_YEAR_KEY) || '1');
            const curSec = secElem ? secElem.value : (localStorage.getItem(PREF_SEC_KEY) || 'CSE - A');
            const curDay = dayElem ? dayElem.value : (localStorage.getItem(PREF_DAY_KEY) || getTodayDayCode());

            // check holiday
            if (document.querySelector('.routine-section') && document.querySelector('.holiday-state')) {
                return;
            }

            const cachedRoutine = localStorage.getItem(STORAGE_ROUTINE_KEY);
            if (cachedRoutine) {
                try {
                    renderRoutineTable(JSON.parse(cachedRoutine), curYear, curSec, curDay);
                } catch(err) {}
            }

            if (!navigator.onLine) {
                if (e && e.preventDefault) e.preventDefault();
                return false;
            }
        }

        filterSelects.forEach(select => {
            select.addEventListener('change', function(e) {
                updateFromSelects(e);
                if (!navigator.onLine) {
                    e.preventDefault();
                    e.stopPropagation();
                    return false;
                }
            });
        });

        filterForms.forEach(form => {
            form.addEventListener('submit', function(e) {
                if (!navigator.onLine) {
                    e.preventDefault();
                    updateFromSelects(e);
                    return false;
                }
            });
        });
    }

    function syncOfflineData() {
        setupFilterChangeHandlers();

        const cachedRoutine = localStorage.getItem(STORAGE_ROUTINE_KEY);
        const cachedNotices = localStorage.getItem(STORAGE_NOTICES_KEY);

        const yearElem = document.getElementById('year') || document.getElementById('yr-select');
        const secElem = document.getElementById('sec') || document.getElementById('sec-select');
        const dayElem = document.getElementById('day');

        const curYear = yearElem ? yearElem.value : (localStorage.getItem(PREF_YEAR_KEY) || '1');
        const curSec = secElem ? secElem.value : (localStorage.getItem(PREF_SEC_KEY) || 'CSE - A');
        const curDay = dayElem ? dayElem.value : (localStorage.getItem(PREF_DAY_KEY) || getTodayDayCode());

        const hasExistingRows = document.querySelector('.routine-table tbody tr');
        const hasHoliday = document.querySelector('.holiday-state') !== null;

        if (cachedNotices && !document.querySelector('#global-notice-wrapper .notice-banner')) {
            try {
                renderNoticeBanner(JSON.parse(cachedNotices));
            } catch (e) { console.error('Notice parse error:', e); }
        }

        // check holiday
        if (cachedRoutine && !hasHoliday && (!hasExistingRows || !navigator.onLine)) {
            try {
                renderRoutineTable(JSON.parse(cachedRoutine), curYear, curSec, curDay);
            } catch (e) { console.error('Routine parse error:', e); }
        }

        // background sync
        fetch('/api/sync-check/')
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    const localRVer = localStorage.getItem(STORAGE_ROUTINE_VER_KEY);
                    const localNVer = localStorage.getItem(STORAGE_NOTICES_VER_KEY);

                    let updated = false;

                    if (data.routine_version !== localRVer || !cachedRoutine) {
                        localStorage.setItem(STORAGE_ROUTINE_KEY, JSON.stringify(data.routine_data));
                        localStorage.setItem(STORAGE_ROUTINE_VER_KEY, data.routine_version);
                        const hasHolidayNow = document.querySelector('.holiday-state') !== null;
                        if (localRVer && !hasHolidayNow) {
                            renderRoutineTable(data.routine_data, curYear, curSec, curDay);
                        }
                        updated = true;
                    }

                    if (data.notice_version !== localNVer || !cachedNotices) {
                        localStorage.setItem(STORAGE_NOTICES_KEY, JSON.stringify(data.notices));
                        localStorage.setItem(STORAGE_NOTICES_VER_KEY, data.notice_version);
                        renderNoticeBanner(data.notices);
                        updated = true;
                    }

                    if (updated) {
                        console.log('⚡ LocalStorage updated instantly with latest Admin changes!');
                    }
                }
            })
            .catch(err => {
                console.log('Network offline or slow; using cached LocalStorage data.', err);
            });
    }

    document.addEventListener('DOMContentLoaded', syncOfflineData);
    
    // refresh slots
    setInterval(() => {
        const hasHolidayNow = document.querySelector('.holiday-state') !== null;
        if (hasHolidayNow && document.querySelector('.routine-section')) {
            return;
        }
        const cachedRoutine = localStorage.getItem(STORAGE_ROUTINE_KEY);
        if (cachedRoutine) {
            const yearElem = document.getElementById('year') || document.getElementById('yr-select');
            const secElem = document.getElementById('sec') || document.getElementById('sec-select');
            const dayElem = document.getElementById('day');
            try {
                renderRoutineTable(
                    JSON.parse(cachedRoutine), 
                    yearElem ? yearElem.value : (localStorage.getItem(PREF_YEAR_KEY) || '1'), 
                    secElem ? secElem.value : (localStorage.getItem(PREF_SEC_KEY) || 'CSE - A'), 
                    dayElem ? dayElem.value : (localStorage.getItem(PREF_DAY_KEY) || getTodayDayCode())
                );
            } catch(e) {}
        }
    }, 30000);


})();
