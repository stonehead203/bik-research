(function () {
    'use strict';

    const STORAGE_PREFIX = 'bik-travel-board-v2';
    const CATEGORY_META = {
        all: { label: '전체', icon: '✦' },
        stay: { label: '숙소', icon: '🏨' },
        food: { label: '맛집', icon: '🍽️' },
        cafe: { label: '카페', icon: '☕' },
        sight: { label: '관광', icon: '🗺️' },
        shop: { label: '쇼핑', icon: '🛍️' },
        other: { label: '기타', icon: '📌' }
    };

    let state = null;
    let tripCollection = null;
    let searchResults = [];
    let selectedPlaceId = '';
    let activeCategory = 'all';
    let activeMobilePanel = 'places';
    let saveTimer = 0;
    let loadGeneration = 0;
    let initialized = false;
    let lastLoadedUser = '';
    let sharedView = false;
    let sharedBy = '';
    let pendingInviteToken = '';
    let collaborationRefreshTimer = 0;
    let travelMap = null;
    let travelMarkerLayer = null;
    let travelRouteLayer = null;

    function uid(prefix) {
        return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    }

    function dateString(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    function addDays(value, amount) {
        const date = new Date(`${value}T12:00:00`);
        date.setDate(date.getDate() + amount);
        return dateString(date);
    }

    function defaultBoard() {
        const start = dateString(new Date());
        return {
            version: 1,
            trip: {
                id: uid('trip'),
                title: '나의 첫 여행',
                destination: '',
                startDate: start,
                endDate: addDays(start, 2),
                activeDay: 0,
                updatedAt: new Date().toISOString()
            },
            places: [],
            itinerary: { 0: [], 1: [], 2: [] },
            scheduleTimes: { 0: {}, 1: {}, 2: {} }
        };
    }

    function cleanText(value, max = 120) {
        return String(value || '').replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim().slice(0, max);
    }

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>'"]/g, char => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
        })[char]);
    }

    function numberOrNull(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : null;
    }

    function normalizeCategory(value) {
        const raw = String(value || '').toLowerCase();
        if (/호텔|숙소|펜션|리조트|모텔|게스트/.test(raw)) return 'stay';
        if (/카페|커피|디저트|베이커리/.test(raw)) return 'cafe';
        if (/음식|한식|일식|중식|양식|식당|레스토랑|주점|요리/.test(raw)) return 'food';
        if (/쇼핑|백화점|시장|마트|상점|몰/.test(raw)) return 'shop';
        if (/관광|명소|공원|박물관|미술관|전시|테마/.test(raw)) return 'sight';
        return CATEGORY_META[value] ? value : 'other';
    }

    function normalizePlace(item, source = 'manual') {
        const name = cleanText(item?.name || item?.title, 80) || '이름 없는 장소';
        const id = cleanText(item?.id, 80).replace(/[^a-zA-Z0-9:_-]/g, '') || uid('place');
        return {
            id,
            name,
            category: normalizeCategory(item?.category),
            categoryLabel: cleanText(item?.categoryLabel || item?.category, 80) || '기타',
            address: cleanText(item?.roadAddress || item?.address, 160),
            link: String(item?.link || '').trim().slice(0, 600),
            lng: numberOrNull(item?.lng ?? item?.mapx),
            lat: numberOrNull(item?.lat ?? item?.mapy),
            note: cleanText(item?.note, 500),
            source,
            savedAt: item?.savedAt || new Date().toISOString()
        };
    }

    function normalizeBoard(payload) {
        const base = defaultBoard();
        const input = payload && typeof payload === 'object' ? payload : {};
        const trip = input.trip && typeof input.trip === 'object' ? input.trip : {};
        const result = {
            version: 1,
            trip: {
                ...base.trip,
                id: cleanText(trip.id, 80) || base.trip.id,
                title: cleanText(trip.title, 80) || base.trip.title,
                destination: cleanText(trip.destination, 80),
                startDate: /^\d{4}-\d{2}-\d{2}$/.test(trip.startDate || '') ? trip.startDate : base.trip.startDate,
                endDate: /^\d{4}-\d{2}-\d{2}$/.test(trip.endDate || '') ? trip.endDate : base.trip.endDate,
                activeDay: Math.max(0, Number(trip.activeDay) || 0),
                updatedAt: trip.updatedAt || base.trip.updatedAt
            },
            places: Array.isArray(input.places) ? input.places.slice(0, 200).map(item => normalizePlace(item, item?.source || 'saved')) : [],
            itinerary: {},
            scheduleTimes: {}
        };
        const collaboration = input.collaboration && typeof input.collaboration === 'object' ? input.collaboration : null;
        if (collaboration?.id) {
            result.collaboration = {
                id: cleanText(collaboration.id, 80),
                owner: cleanText(collaboration.owner, 100),
                ownerName: cleanText(collaboration.ownerName, 40),
                role: cleanText(collaboration.role, 20) || 'editor',
                revision: Math.max(1, Number(collaboration.revision) || 1),
                memberCount: Math.max(1, Number(collaboration.memberCount) || 1)
            };
        }
        const ids = new Set(result.places.map(place => place.id));
        const sourceItinerary = input.itinerary && typeof input.itinerary === 'object' ? input.itinerary : {};
        Object.entries(sourceItinerary).slice(0, 31).forEach(([day, values]) => {
            result.itinerary[String(Math.max(0, Number(day) || 0))] = Array.isArray(values)
                ? [...new Set(values.map(String).filter(id => ids.has(id)))].slice(0, 30)
                : [];
        });
        const sourceTimes = input.scheduleTimes && typeof input.scheduleTimes === 'object' ? input.scheduleTimes : {};
        Object.entries(sourceTimes).slice(0, 31).forEach(([day, values]) => {
            const dayKey = String(Math.max(0, Number(day) || 0));
            result.scheduleTimes[dayKey] = {};
            if (!values || typeof values !== 'object') return;
            Object.entries(values).forEach(([placeId, value]) => {
                const time = /^([01]\d|2[0-3]):[0-5]\d$/.test(String(value || '')) ? String(value) : '';
                if (ids.has(placeId) && time) result.scheduleTimes[dayKey][placeId] = time;
            });
        });
        ensureDayBuckets(result);
        return result;
    }

    function normalizeCollection(payload) {
        if (payload && Number(payload.version) === 2 && Array.isArray(payload.trips)) {
            const seen = new Set();
            const trips = payload.trips.slice(0, 20).map(normalizeBoard).filter(board => {
                if (seen.has(board.trip.id)) return false;
                seen.add(board.trip.id);
                return true;
            });
            if (!trips.length) trips.push(defaultBoard());
            const requestedId = cleanText(payload.activeTripId, 80);
            return {
                version: 2,
                activeTripId: trips.some(board => board.trip.id === requestedId) ? requestedId : trips[0].trip.id,
                trips
            };
        }
        const legacyBoard = normalizeBoard(payload);
        return { version: 2, activeTripId: legacyBoard.trip.id, trips: [legacyBoard] };
    }

    function mergeSharedTrips(collection, sharedTrips) {
        const result = collection || normalizeCollection(null);
        (Array.isArray(sharedTrips) ? sharedTrips : []).forEach(item => {
            const board = normalizeBoard(item);
            const index = result.trips.findIndex(existing => existing.trip.id === board.trip.id);
            if (index >= 0) result.trips[index] = board;
            else result.trips.push(board);
        });
        return result;
    }

    function personalCollectionPayload() {
        const personalTrips = (tripCollection?.trips || []).filter(board => !board.collaboration?.id);
        const activeTripId = personalTrips.some(board => board.trip.id === tripCollection?.activeTripId)
            ? tripCollection.activeTripId
            : (personalTrips[0]?.trip.id || '');
        return { version: 2, activeTripId, trips: personalTrips };
    }

    function savedStatusText() {
        if (state?.collaboration?.id) return `공동 여행 · ${state.collaboration.memberCount}명 · 저장됨`;
        return '계정에 저장됨';
    }

    function activateTrip(id) {
        if (!tripCollection) tripCollection = normalizeCollection(null);
        const next = tripCollection.trips.find(board => board.trip.id === id) || tripCollection.trips[0];
        tripCollection.activeTripId = next.trip.id;
        state = next;
        searchResults = [];
        selectedPlaceId = '';
        activeCategory = 'all';
        return next;
    }

    function tripDays(board = state) {
        if (!board) return 1;
        const start = new Date(`${board.trip.startDate}T12:00:00`);
        const end = new Date(`${board.trip.endDate}T12:00:00`);
        const days = Math.floor((end - start) / 86400000) + 1;
        return Math.max(1, Math.min(14, Number.isFinite(days) ? days : 1));
    }

    function ensureDayBuckets(board = state) {
        const days = tripDays(board);
        for (let index = 0; index < days; index += 1) {
            if (!Array.isArray(board.itinerary[index])) board.itinerary[index] = [];
            if (!board.scheduleTimes || typeof board.scheduleTimes !== 'object') board.scheduleTimes = {};
            if (!board.scheduleTimes[index] || typeof board.scheduleTimes[index] !== 'object') board.scheduleTimes[index] = {};
        }
        board.trip.activeDay = Math.min(Math.max(0, board.trip.activeDay || 0), days - 1);
    }

    function normalizedUserId(value) {
        return String(value || '').trim().toLowerCase();
    }

    function storageKeyForUser(user = '') {
        const normalized = normalizedUserId(user);
        return `${STORAGE_PREFIX}:${normalized ? `user:${encodeURIComponent(normalized)}` : 'guest'}`;
    }

    function localLoad(user = '') {
        try {
            return normalizeCollection(JSON.parse(localStorage.getItem(storageKeyForUser(user)) || 'null'));
        } catch (_) {
            return normalizeCollection(null);
        }
    }

    function hasLocalBoard(user = '') {
        return Boolean(localStorage.getItem(storageKeyForUser(user)));
    }

    function setSyncStatus(text, type = '') {
        const target = document.getElementById('travel-sync-state');
        if (!target) return;
        target.textContent = text;
        target.className = `travel-sync-state${type ? ` is-${type}` : ''}`;
    }

    function sharedTokenFromPath() {
        const match = window.location.pathname.match(/^\/Travel\/Share\/([A-Za-z0-9_-]{12,40})/i);
        return match ? match[1] : '';
    }

    function inviteTokenFromPath() {
        const match = window.location.pathname.match(/^\/Travel\/Join\/([A-Za-z0-9_-]{12,64})/i);
        return match ? match[1] : '';
    }

    async function loadTravelInvite(token) {
        pendingInviteToken = token;
        const panel = document.getElementById('travel-invite-panel');
        const response = await fetch(`/api/travel/invite/${encodeURIComponent(token)}`, { credentials: 'same-origin', cache: 'no-store' });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || '초대 정보를 불러오지 못했습니다.');
        document.getElementById('travel-invite-title').textContent = data.trip.title;
        document.getElementById('travel-invite-meta').textContent = `${data.ownerName}님의 공동 여행 · ${data.trip.startDate} ~ ${data.trip.endDate}`;
        panel?.classList.remove('hidden-content');
        document.getElementById('content-travel')?.classList.remove('travel-board-entered');
    }

    async function loadSharedBoard(token) {
        setSyncStatus('공유 일정을 불러오는 중', 'saving');
        const response = await fetch(`/api/travel/share/${encodeURIComponent(token)}`, { cache: 'no-store' });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || '공유 일정을 불러오지 못했습니다.');
        tripCollection = null;
        state = normalizeBoard(data.board);
        sharedView = true;
        sharedBy = cleanText(data.sharedBy, 40) || 'BIK 사용자';
        lastLoadedUser = '';
        setSyncStatus(`${sharedBy}님의 공유 일정 · 읽기 전용`, 'saved');
        renderAll();
    }

    async function loadBoard() {
        const generation = ++loadGeneration;
        window.clearTimeout(saveTimer);
        saveTimer = 0;
        tripCollection = null;
        state = null;
        searchResults = [];
        selectedPlaceId = '';
        const loggedIn = typeof authState !== 'undefined' && Boolean(authState.loggedIn);
        const user = loggedIn ? String(authState.loginId || authState.username || '') : '';
        if (!loggedIn) {
            tripCollection = localLoad('');
            activateTrip(tripCollection.activeTripId);
            lastLoadedUser = '';
            setSyncStatus('이 기기에 저장', 'saved');
            document.getElementById('content-travel')?.classList.remove('travel-board-entered');
            renderAll();
            return;
        }
        setSyncStatus('여행 보드 불러오는 중', 'saving');
        try {
            const response = await fetch('/api/travel/board', { credentials: 'same-origin', cache: 'no-store' });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || 'load failed');
            const activeUser = typeof authState !== 'undefined' && authState.loggedIn ? String(authState.loginId || authState.username || '') : '';
            if (generation !== loadGeneration || normalizedUserId(activeUser) !== normalizedUserId(user)) return;
            const remote = data.board ? normalizeCollection(data.board) : null;
            const local = localLoad(user);
            tripCollection = mergeSharedTrips(remote || local, data.sharedTrips);
            activateTrip(tripCollection.activeTripId);
            lastLoadedUser = user;
            if (!remote && hasLocalBoard(user)) scheduleSave(true);
            setSyncStatus('계정에 저장됨', 'saved');
        } catch (error) {
            const activeUser = typeof authState !== 'undefined' && authState.loggedIn ? String(authState.loginId || authState.username || '') : '';
            if (generation !== loadGeneration || normalizedUserId(activeUser) !== normalizedUserId(user)) return;
            tripCollection = localLoad(user);
            activateTrip(tripCollection.activeTripId);
            lastLoadedUser = user;
            setSyncStatus('로컬 저장 모드', 'error');
        }
        document.getElementById('content-travel')?.classList.remove('travel-board-entered');
        renderAll();
    }

    async function saveBoardNow() {
        if (!state || sharedView) return;
        state.trip.updatedAt = new Date().toISOString();
        const loggedIn = typeof authState !== 'undefined' && Boolean(authState.loggedIn);
        const user = loggedIn ? String(authState.loginId || authState.username || '') : '';
        if (!loggedIn || normalizedUserId(user) !== normalizedUserId(lastLoadedUser)) return;
        setSyncStatus(state.collaboration?.id ? '공동 여행 저장 중' : '저장 중', 'saving');
        try {
            if (state.collaboration?.id) {
                const response = await fetch(`/api/travel/collaboration/${encodeURIComponent(state.collaboration.id)}`, {
                    method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ board: state, revision: state.collaboration.revision })
                });
                const data = await response.json();
                if (response.status === 409 && data.board) {
                    const latest = normalizeBoard({ ...data.board, collaboration: data.collaboration });
                    const index = tripCollection.trips.findIndex(board => board.trip.id === state.trip.id);
                    if (index >= 0) tripCollection.trips[index] = latest;
                    state = latest;
                    renderAll();
                    throw new Error('다른 참여자가 먼저 수정했습니다. 최신 일정으로 다시 불러왔어요.');
                }
                if (!response.ok || !data.ok) throw new Error(data.error || '공동 여행을 저장하지 못했습니다.');
                state.collaboration = data.collaboration;
                setSyncStatus(savedStatusText(), 'saved');
                return;
            }
            if (!tripCollection) tripCollection = normalizeCollection(state);
            tripCollection.activeTripId = state.trip.id;
            const index = tripCollection.trips.findIndex(board => board.trip.id === state.trip.id);
            if (index >= 0) tripCollection.trips[index] = state;
            else tripCollection.trips.push(state);
            const personal = personalCollectionPayload();
            localStorage.setItem(storageKeyForUser(user), JSON.stringify(personal));
            const response = await fetch('/api/travel/board', {
                method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(personal)
            });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || 'save failed');
            setSyncStatus('계정에 저장됨', 'saved');
        } catch (error) {
            setSyncStatus(error.message || '저장하지 못했습니다.', 'error');
        }
    }

    function scheduleSave(immediate = false) {
        window.clearTimeout(saveTimer);
        if (immediate) void saveBoardNow();
        else saveTimer = window.setTimeout(saveBoardNow, 500);
    }

    function placeById(id) {
        return state?.places.find(place => place.id === id)
            || searchResults.find(place => place.id === id)
            || null;
    }

    function selectedPlace() {
        return placeById(selectedPlaceId);
    }

    function activeDayIds() {
        return state?.itinerary?.[state.trip.activeDay] || [];
    }

    function activeDayTimes() {
        return state?.scheduleTimes?.[state.trip.activeDay] || {};
    }

    function sortedActiveDayIds() {
        const times = activeDayTimes();
        return activeDayIds().map((id, index) => ({ id, index, time: times[id] || '' }))
            .sort((a, b) => {
                if (a.time && b.time) return a.time.localeCompare(b.time) || a.index - b.index;
                if (a.time) return -1;
                if (b.time) return 1;
                return a.index - b.index;
            }).map(item => item.id);
    }


    function koreanTimeLabel(value) {
        if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(String(value || ''))) return '시간 미정';
        const [hourText, minute] = value.split(':');
        const hour = Number(hourText);
        const period = hour < 12 ? '오전' : '오후';
        const displayHour = hour % 12 || 12;
        return `${period} ${String(displayHour).padStart(2, '0')}:${minute}`;
    }

    function detailTimeParts(value) {
        const valid = /^([01]\d|2[0-3]):[0-5]\d$/.test(String(value || '')) ? value : '09:00';
        const [hourText, minuteText] = valid.split(':');
        const hour = Number(hourText);
        return { period: hour < 12 ? 'am' : 'pm', hour: String(hour % 12 || 12), minute: String(Math.floor(Number(minuteText) / 5) * 5).padStart(2, '0') };
    }

    function optionHtml(value, label, selected) {
        return `<option value="${escapeHtml(value)}"${String(value) === String(selected) ? ' selected' : ''}>${escapeHtml(label)}</option>`;
    }

    function formatDayLabel(index) {
        const date = addDays(state.trip.startDate, index);
        return `${Number(date.slice(5, 7))}/${Number(date.slice(8, 10))}`;
    }

    function renderTripFields() {
        const title = document.getElementById('travel-title-input');
        const destination = document.getElementById('travel-destination-input');
        const start = document.getElementById('travel-start-input');
        const end = document.getElementById('travel-end-input');
        if (title && title !== document.activeElement) title.value = state.trip.title;
        if (destination && destination !== document.activeElement) destination.value = state.trip.destination;
        if (start && start !== document.activeElement) start.value = state.trip.startDate;
        if (end && end !== document.activeElement) end.value = state.trip.endDate;
        [title, destination, start, end].forEach(input => { if (input) input.disabled = sharedView; });
        const heading = document.getElementById('travel-trip-heading');
        if (heading) heading.textContent = state.trip.title;
    }

    function renderDayStrip() {
        const target = document.getElementById('travel-day-strip');
        if (!target) return;
        target.innerHTML = Array.from({ length: tripDays() }, (_, index) => `
            <button type="button" class="travel-day-button${index === state.trip.activeDay ? ' active' : ''}" onclick="setTravelDay(${index})">
                <strong>DAY ${index + 1}</strong>${formatDayLabel(index)}
            </button>`).join('');
    }

    function renderItinerary() {
        const target = document.getElementById('travel-itinerary');
        if (!target) return;
        const places = sortedActiveDayIds().map(placeById).filter(Boolean);
        const times = activeDayTimes();
        target.ondragover = sharedView ? null : event => event.preventDefault();
        target.ondrop = sharedView ? null : event => {
            event.preventDefault();
            const id = event.dataTransfer?.getData('text/travel-place');
            if (id) addTravelPlaceToDay(id);
        };
        if (!places.length) {
            target.innerHTML = '<div class="travel-empty"><div><strong>아직 일정이 비어 있어요</strong>장소 카드의 + 버튼을 누르거나<br>여기로 끌어다 놓으세요.</div></div>';
            return;
        }
        target.innerHTML = places.map((place, index) => `
            <article class="travel-slot" data-index="${index + 1}" ${sharedView ? '' : 'draggable="true"'} data-place-id="${escapeHtml(place.id)}" onclick="selectTravelPlace('${escapeHtml(place.id)}')">
                <span class="travel-slot-time${times[place.id] ? ' is-set' : ''}">${escapeHtml(koreanTimeLabel(times[place.id]))}</span>
                <strong>${escapeHtml(place.name)}</strong>
                <span>${escapeHtml(place.address || place.categoryLabel)}</span>
                ${sharedView ? '' : `<button type="button" class="travel-slot-remove" aria-label="일정에서 제거" onclick="event.stopPropagation();removeTravelPlaceFromDay('${escapeHtml(place.id)}')">×</button>`}
            </article>`).join('');
        if (!sharedView) target.querySelectorAll('[draggable="true"]').forEach(card => {
            card.addEventListener('dragstart', event => event.dataTransfer?.setData('text/travel-place', card.dataset.placeId || ''));
        });
    }

    function candidateCard(place, isSearchResult = false) {
        const meta = CATEGORY_META[place.category] || CATEGORY_META.other;
        const saved = state.places.some(item => item.id === place.id);
        return `
            <article class="travel-place-card${selectedPlaceId === place.id ? ' active' : ''}" onclick="selectTravelPlace('${escapeHtml(place.id)}')" draggable="true" data-place-id="${escapeHtml(place.id)}">
                <span class="travel-place-icon" aria-hidden="true">${meta.icon}</span>
                <span class="travel-place-meta">
                    <strong>${escapeHtml(place.name)}</strong>
                    <span>${escapeHtml(place.address || place.categoryLabel || meta.label)}</span>
                </span>
                <span class="travel-place-actions">
                    ${!sharedView && isSearchResult && !saved ? `<button type="button" class="travel-card-button" title="후보에 저장" onclick="event.stopPropagation();saveTravelCandidate('${escapeHtml(place.id)}')">♡</button>` : ''}
                    ${!sharedView && saved ? `<button type="button" class="travel-card-button is-add" title="현재 날짜에 추가" onclick="event.stopPropagation();addTravelPlaceToDay('${escapeHtml(place.id)}')">+</button>` : ''}
                </span>
            </article>`;
    }

    function renderCandidates() {
        const target = document.getElementById('travel-candidate-list');
        if (!target) return;
        const matches = place => activeCategory === 'all' || place.category === activeCategory;
        const resultItems = searchResults.filter(matches);
        const savedItems = state.places.filter(matches);
        let html = '';
        if (resultItems.length) {
            html += '<span class="travel-column-label" style="margin:2px 2px 0">검색 결과</span>';
            html += resultItems.map(place => candidateCard(place, true)).join('');
        }
        if (savedItems.length) {
            html += '<span class="travel-column-label" style="margin:8px 2px 0">내 후보 장소</span>';
            html += savedItems.map(place => candidateCard(place, false)).join('');
        }
        if (!html) html = '<div class="travel-empty"><div><strong>가고 싶은 곳을 검색해보세요</strong>숙소, 식당, 카페를 후보로 모은 뒤<br>일정에 바로 배치할 수 있어요.</div></div>';
        target.innerHTML = html;
        target.querySelectorAll('[draggable="true"]').forEach(card => {
            card.addEventListener('dragstart', event => event.dataTransfer?.setData('text/travel-place', card.dataset.placeId || ''));
        });
        document.querySelectorAll('.travel-category-chip').forEach(button => button.classList.toggle('active', button.dataset.category === activeCategory));
    }

    function mapPoint(place, index, all) {
        const withCoordinates = all.filter(item => Number.isFinite(item.lat) && Number.isFinite(item.lng));
        if (withCoordinates.length >= 2 && Number.isFinite(place.lat) && Number.isFinite(place.lng)) {
            const lngs = withCoordinates.map(item => item.lng);
            const lats = withCoordinates.map(item => item.lat);
            const minLng = Math.min(...lngs), maxLng = Math.max(...lngs);
            const minLat = Math.min(...lats), maxLat = Math.max(...lats);
            return {
                x: 12 + ((place.lng - minLng) / Math.max(.00001, maxLng - minLng)) * 76,
                y: 84 - ((place.lat - minLat) / Math.max(.00001, maxLat - minLat)) * 68
            };
        }
        const angle = (index / Math.max(1, all.length)) * Math.PI * 2 - Math.PI / 2;
        return { x: 50 + Math.cos(angle) * 30, y: 50 + Math.sin(angle) * 28 };
    }

    function leafletMarkerIcon(index, active) {
        return window.L.divIcon({
            className: '',
            html: `<span class="travel-leaflet-marker${active ? ' is-active' : ''}"><span>${index + 1}</span></span>`,
            iconSize: active ? [35, 35] : [30, 30],
            iconAnchor: active ? [17, 34] : [15, 29]
        });
    }

    function ensureTravelMap() {
        const target = document.getElementById('travel-map-canvas');
        if (!target || !window.L) return null;
        if (travelMap) return travelMap;
        travelMap = window.L.map(target, { zoomControl: true, attributionControl: true, preferCanvas: true });
        window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors'
        }).addTo(travelMap);
        travelMarkerLayer = window.L.layerGroup().addTo(travelMap);
        travelRouteLayer = window.L.layerGroup().addTo(travelMap);
        travelMap.setView([37.5665, 126.978], 11);
        return travelMap;
    }

    function renderMap() {
        const target = document.getElementById('travel-map-canvas');
        if (!target) return;
        target.querySelector('.travel-map-empty')?.remove();
        target.querySelector('.travel-map-no-coordinates')?.remove();
        const map = ensureTravelMap();
        if (!map) {
            target.insertAdjacentHTML('beforeend', '<div class="travel-map-empty">지도를 불러오는 중입니다.</div>');
            return;
        }
        travelMarkerLayer.clearLayers();
        travelRouteLayer.clearLayers();
        const selected = selectedPlace();
        const scheduled = sortedActiveDayIds().map(placeById).filter(Boolean);
        const pool = [...state.places];
        if (selected && !pool.some(place => place.id === selected.id)) pool.unshift(selected);
        const base = scheduled.length ? scheduled : pool;
        const located = base.filter(place => Number.isFinite(place.lat) && Number.isFinite(place.lng));
        if (!located.length) {
            target.insertAdjacentHTML('beforeend', '<div class="travel-map-no-coordinates">검색으로 저장한 장소부터 실제 지도에 표시됩니다.</div>');
            map.setView([37.5665, 126.978], 11);
            window.setTimeout(() => map.invalidateSize(), 0);
            return;
        }
        located.forEach((place, index) => {
            const marker = window.L.marker([place.lat, place.lng], { icon: leafletMarkerIcon(index, selectedPlaceId === place.id), title: place.name });
            marker.on('click', () => selectTravelPlace(place.id));
            marker.bindTooltip(place.name, { direction: 'top', offset: [0, -25], opacity: .92 });
            marker.addTo(travelMarkerLayer);
        });
        const routePoints = scheduled.filter(place => Number.isFinite(place.lat) && Number.isFinite(place.lng)).map(place => [place.lat, place.lng]);
        if (routePoints.length > 1) {
            window.L.polyline(routePoints, { color: '#ff6b4a', weight: 3, opacity: .88, dashArray: '8 7' }).addTo(travelRouteLayer);
        }
        const focus = selected && Number.isFinite(selected.lat) && Number.isFinite(selected.lng) ? [selected.lat, selected.lng] : null;
        if (focus) map.setView(focus, Math.max(map.getZoom(), 15), { animate: false });
        else if (located.length === 1) map.setView([located[0].lat, located[0].lng], 15, { animate: false });
        else map.fitBounds(window.L.latLngBounds(located.map(place => [place.lat, place.lng])), { padding: [34, 34], maxZoom: 15, animate: false });
        window.setTimeout(() => map.invalidateSize(), 0);
    }

    function naverReviewUrl(place) {
        const query = `${place.name} ${place.address || state.trip.destination || ''} 후기`.trim();
        return `https://search.naver.com/search.naver?query=${encodeURIComponent(query)}`;
    }

    function renderDetail() {
        const target = document.getElementById('travel-detail');
        if (!target) return;
        const place = selectedPlace();
        if (!place) {
            target.innerHTML = '<div class="travel-detail-empty"><div><strong>장소를 선택해보세요</strong>상세를 닫지 않고 후보 장소를<br>연속해서 비교할 수 있어요.</div></div>';
            return;
        }
        const meta = CATEGORY_META[place.category] || CATEGORY_META.other;
        const saved = state.places.some(item => item.id === place.id);
        const scheduled = activeDayIds().includes(place.id);
        const timeValue = activeDayTimes()[place.id] || '';
        const parts = detailTimeParts(timeValue);
        const minuteOptions = Array.from({ length: 12 }, (_, index) => String(index * 5).padStart(2, '0'));
        const editActions = sharedView
            ? `<button type="button" class="travel-quiet-button" onclick="openTravelReview('${escapeHtml(place.id)}')">네이버 후기 보기 ↗</button>`
            : `${saved
                ? `<button type="button" class="travel-primary-button" onclick="addTravelPlaceToDay('${escapeHtml(place.id)}')">${scheduled ? `DAY ${state.trip.activeDay + 1}에 추가됨` : `DAY ${state.trip.activeDay + 1}에 추가`}</button>`
                : `<button type="button" class="travel-primary-button" onclick="saveTravelCandidate('${escapeHtml(place.id)}')">후보로 저장</button>`}
               <button type="button" class="travel-quiet-button" onclick="openTravelReview('${escapeHtml(place.id)}')">네이버 후기 보기 ↗</button>`;
        const timeEditor = !sharedView && saved && scheduled ? `
            <section class="travel-time-editor">
                <div class="travel-detail-section-head"><div><span>DAY ${state.trip.activeDay + 1}</span><strong>방문 시간</strong></div><button type="button" onclick="clearTravelTime('${escapeHtml(place.id)}')">시간 지우기</button></div>
                <div class="travel-time-selects">
                    <select id="travel-time-period" class="travel-select" aria-label="오전 오후" onchange="updateTravelTimeFromDetail('${escapeHtml(place.id)}')">${optionHtml('am', '오전', parts.period)}${optionHtml('pm', '오후', parts.period)}</select>
                    <select id="travel-time-hour" class="travel-select" aria-label="시" onchange="updateTravelTimeFromDetail('${escapeHtml(place.id)}')">${Array.from({ length: 12 }, (_, index) => optionHtml(String(index + 1), `${index + 1}시`, parts.hour)).join('')}</select>
                    <select id="travel-time-minute" class="travel-select" aria-label="분" onchange="updateTravelTimeFromDetail('${escapeHtml(place.id)}')">${minuteOptions.map(minute => optionHtml(minute, `${minute}분`, parts.minute)).join('')}</select>
                </div>
            </section>` : '';
        const noteArea = saved ? (sharedView
            ? `<div class="travel-shared-note"><span>메모</span><p>${escapeHtml(place.note || '등록된 메모가 없습니다.')}</p></div>`
            : `<label class="travel-note-label" for="travel-place-note">내 메모</label>
               <textarea id="travel-place-note" class="travel-note-input" maxlength="500" placeholder="예약 포인트, 먹고 싶은 메뉴, 동행자 의견을 적어두세요." oninput="updateTravelPlaceNote('${escapeHtml(place.id)}', this.value)">${escapeHtml(place.note || '')}</textarea>
               <button type="button" class="travel-quiet-button travel-remove-candidate" onclick="removeTravelCandidate('${escapeHtml(place.id)}')">후보에서 삭제</button>`) : '';
        target.innerHTML = `
            <span class="travel-detail-category">${escapeHtml(place.categoryLabel || meta.label)}</span>
            <h3>${escapeHtml(place.name)}</h3>
            <p class="travel-detail-address">${escapeHtml(place.address || '주소 정보가 없습니다.')}</p>
            <div class="travel-detail-actions${sharedView ? ' is-single' : ''}">${editActions}</div>
            ${timeEditor}
            ${noteArea}
            <p class="travel-source-note">네이버 공식 지역검색은 장소 정보만 제공합니다. 방문자 리뷰 전문은 복제하지 않고 네이버 검색에서 확인하도록 연결합니다.</p>`;
    }

    function renderMobilePanels() {
        document.querySelectorAll('.travel-column').forEach(column => column.classList.toggle('mobile-active', column.dataset.mobilePanel === activeMobilePanel));
        document.querySelectorAll('[data-travel-mobile-tab]').forEach(button => button.classList.toggle('active', button.dataset.travelMobileTab === activeMobilePanel));
    }

    function renderEntryScreen() {
        const target = document.getElementById('travel-trip-list');
        if (!target || sharedView) return;
        const trips = tripCollection?.trips || [];
        target.innerHTML = trips.map((board, index) => {
            const destination = board.trip.destination || '지역 미정';
            const dateRange = `${board.trip.startDate.replaceAll('-', '.')} — ${board.trip.endDate.replaceAll('-', '.')}`;
            const collaborative = Boolean(board.collaboration?.id);
            return `<article class="travel-trip-card${collaborative ? ' is-collaborative' : ''}" role="button" tabindex="0" aria-label="${escapeHtml(board.trip.title)} 열기" onclick="openTravelTrip('${escapeHtml(board.trip.id)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openTravelTrip('${escapeHtml(board.trip.id)}')}">
                ${collaborative ? '' : `<button type="button" class="travel-trip-delete" aria-label="${escapeHtml(board.trip.title)} 삭제" onclick="event.stopPropagation(); deleteTravelTrip('${escapeHtml(board.trip.id)}')">×</button>`}
                <div class="travel-trip-card-top"><span class="travel-trip-number">${collaborative ? `👥 함께 편집 · ${board.collaboration.memberCount}명` : `TRIP ${String(index + 1).padStart(2, '0')}`}</span><span aria-hidden="true">${collaborative ? '🌐' : '🧳'}</span></div>
                <h2>${escapeHtml(board.trip.title)}</h2>
                <p class="travel-trip-destination">${escapeHtml(destination)}</p>
                <p class="travel-trip-dates">${escapeHtml(dateRange)}</p>
                <div class="travel-trip-card-foot"><span>후보 ${board.places.length}곳</span><span>${tripDays(board)}일 일정</span><b>열기 →</b></div>
            </article>`;
        }).join('');
    }

    function renderAll() {
        if (!state) return;
        ensureDayBuckets();
        renderEntryScreen();
        renderTripFields();
        renderDayStrip();
        renderItinerary();
        renderCandidates();
        renderMap();
        renderDetail();
        renderMobilePanels();
        const travelPage = document.getElementById('content-travel');
        travelPage?.classList.toggle('is-shared-view', sharedView);
        if (sharedView) travelPage?.classList.add('travel-board-entered');
        const shareButton = document.getElementById('travel-share-button');
        if (shareButton) shareButton.textContent = sharedView ? '링크 공유' : '공동 편집 초대';
    }

    async function searchPlaces(event) {
        event?.preventDefault?.();
        const input = document.getElementById('travel-search-input');
        const meta = document.getElementById('travel-search-meta');
        const query = cleanText(input?.value, 100);
        if (!query) {
            searchResults = [];
            selectedPlaceId = '';
            activeCategory = 'all';
            if (meta) meta.textContent = '장소를 선택해도 이 화면을 벗어나지 않아요.';
            renderCandidates();
            renderMap();
            renderDetail();
            setTravelMobilePanel('places');
            input?.focus();
            return;
        }
        if (meta) meta.textContent = '장소를 찾는 중...';
        const button = document.getElementById('travel-search-button');
        if (button) button.disabled = true;
        try {
            const destination = state?.trip?.destination || '';
            const response = await fetch(`/api/travel/places?q=${encodeURIComponent(query)}&destination=${encodeURIComponent(destination)}`, { cache: 'no-store' });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || 'search failed');
            searchResults = (data.items || []).map(item => normalizePlace(item, 'naver'));
            if (meta) meta.textContent = searchResults.length ? `${searchResults.length}개의 장소 · 후보로 저장하거나 일정에 추가하세요.` : '검색 결과가 없습니다. 장소명과 지역을 함께 입력해보세요.';
        } catch (error) {
            searchResults = [];
            if (meta) meta.textContent = '장소 검색 연결이 필요합니다. 우측의 직접 추가를 이용할 수 있어요.';
        } finally {
            if (button) button.disabled = false;
            renderCandidates();
        }
    }

    window.initTravelBoard = async function initTravelBoard(force = false) {
        if (!document.getElementById('content-travel')) return;
        const shareToken = sharedTokenFromPath();
        const inviteToken = inviteTokenFromPath();
        if (shareToken) {
            if (initialized && sharedView && !force) { renderAll(); return; }
            initialized = true;
            try { await loadSharedBoard(shareToken); }
            catch (error) { setSyncStatus(error.message || '공유 일정을 불러오지 못했습니다.', 'error'); }
            return;
        }
        sharedView = false;
        sharedBy = '';
        const loggedIn = typeof authState !== 'undefined' && Boolean(authState.loggedIn);
        const user = loggedIn ? String(authState.loginId || authState.username || '') : '';
        if (!loggedIn) {
            sessionStorage.setItem('bik-pending-tab', 'travel');
            if (typeof toggleLoginModal === 'function') toggleLoginModal(true);
            return;
        }
        if (initialized && !force && user === lastLoadedUser) {
            if (saveTimer) await saveBoardNow();
            await loadBoard();
            if (inviteToken) await loadTravelInvite(inviteToken);
            return;
        }
        initialized = true;
        await loadBoard();
        if (inviteToken) await loadTravelInvite(inviteToken);
    };

    window.searchTravelPlaces = searchPlaces;

    window.enterTravelBoard = function enterTravelBoard() {
        const page = document.getElementById('content-travel');
        page?.classList.add('travel-board-entered');
        renderAll();
        window.setTimeout(() => travelMap?.invalidateSize(), 0);
    };


    window.openTravelTrip = function openTravelTrip(id) {
        if (sharedView || !tripCollection) return;
        activateTrip(id);
        document.getElementById('content-travel')?.classList.add('travel-board-entered');
        renderAll();
        if (!state.collaboration?.id) scheduleSave();
        window.setTimeout(() => travelMap?.invalidateSize(), 0);
    };

    window.showTravelTrips = function showTravelTrips() {
        if (sharedView) return;
        document.getElementById('content-travel')?.classList.remove('travel-board-entered');
        renderEntryScreen();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    window.createTravelTrip = function createTravelTrip() {
        if (sharedView) return;
        if (!tripCollection) tripCollection = normalizeCollection(null);
        if (tripCollection.trips.length >= 20) {
            window.alert('여행은 최대 20개까지 만들 수 있습니다.');
            return;
        }
        const board = defaultBoard();
        board.trip.title = `새 여행 ${tripCollection.trips.length + 1}`;
        tripCollection.trips.push(board);
        activateTrip(board.trip.id);
        document.getElementById('content-travel')?.classList.add('travel-board-entered');
        renderAll();
        scheduleSave(true);
        window.setTimeout(() => document.getElementById('travel-title-input')?.select(), 0);
    };

    window.deleteTravelTrip = function deleteTravelTrip(id) {
        if (sharedView || !tripCollection) return;
        const board = tripCollection.trips.find(item => item.trip.id === id);
        if (!board || !window.confirm(`'${board.trip.title}' 여행을 삭제할까요?\n저장한 장소와 일정도 함께 삭제됩니다.`)) return;
        tripCollection.trips = tripCollection.trips.filter(item => item.trip.id !== id);
        if (!tripCollection.trips.length) tripCollection.trips.push(defaultBoard());
        activateTrip(tripCollection.trips[0].trip.id);
        renderAll();
        scheduleSave(true);
    };

    window.updateTravelTrip = function updateTravelTrip(field, value) {
        if (sharedView) return;
        if (!state || !['title', 'destination', 'startDate', 'endDate'].includes(field)) return;
        const next = cleanText(value, 80);
        if ((field === 'startDate' || field === 'endDate') && !/^\d{4}-\d{2}-\d{2}$/.test(next)) return;
        state.trip[field] = next;
        if (state.trip.endDate < state.trip.startDate) state.trip.endDate = state.trip.startDate;
        ensureDayBuckets();
        renderAll();
        scheduleSave();
    };

    window.setTravelDay = function setTravelDay(index) {
        state.trip.activeDay = Math.min(Math.max(0, Number(index) || 0), tripDays() - 1);
        renderAll();
        if (!sharedView) scheduleSave();
    };

    window.setTravelCategory = function setTravelCategory(category) {
        if (!CATEGORY_META[category]) return;
        activeCategory = category;
        renderCandidates();
    };

    window.setTravelMobilePanel = function setTravelMobilePanel(panel) {
        if (!['schedule', 'places', 'map'].includes(panel)) return;
        activeMobilePanel = panel;
        renderMobilePanels();
        if (panel === 'map' && travelMap) window.setTimeout(() => travelMap.invalidateSize(), 0);
    };

    window.selectTravelPlace = function selectTravelPlace(id) {
        if (!placeById(id)) return;
        selectedPlaceId = id;
        renderCandidates();
        renderMap();
        renderDetail();
        if (window.innerWidth <= 900) setTravelMobilePanel('map');
    };

    window.saveTravelCandidate = function saveTravelCandidate(id) {
        if (sharedView) return;
        const source = placeById(id);
        if (!source || state.places.some(place => place.id === id)) return;
        const place = normalizePlace({ ...source, id }, source.source || 'saved');
        state.places.unshift(place);
        searchResults = searchResults.filter(item => item.id !== id);
        selectedPlaceId = place.id;
        renderAll();
        scheduleSave();
    };

    window.addTravelPlaceToDay = function addTravelPlaceToDay(id) {
        if (sharedView) return;
        let place = state.places.find(item => item.id === id);
        if (!place) {
            const source = placeById(id);
            if (!source) return;
            place = normalizePlace({ ...source, id }, source.source || 'saved');
            state.places.unshift(place);
            searchResults = searchResults.filter(item => item.id !== id);
        }
        const bucket = state.itinerary[state.trip.activeDay];
        if (!bucket.includes(place.id)) bucket.push(place.id);
        selectedPlaceId = place.id;
        renderAll();
        scheduleSave();
    };

    window.updateTravelTimeFromDetail = function updateTravelTimeFromDetail(id) {
        if (sharedView || !activeDayIds().includes(id)) return;
        const period = document.getElementById('travel-time-period')?.value === 'pm' ? 'pm' : 'am';
        const hour12 = Math.max(1, Math.min(12, Number(document.getElementById('travel-time-hour')?.value || 9)));
        const minute = Math.max(0, Math.min(55, Math.floor(Number(document.getElementById('travel-time-minute')?.value || 0) / 5) * 5));
        const hour24 = period === 'am' ? hour12 % 12 : (hour12 % 12) + 12;
        state.scheduleTimes[state.trip.activeDay][id] = `${String(hour24).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
        renderItinerary();
        renderMap();
        scheduleSave();
    };

    window.clearTravelTime = function clearTravelTime(id) {
        if (sharedView || !activeDayIds().includes(id)) return;
        delete state.scheduleTimes[state.trip.activeDay][id];
        renderItinerary();
        renderDetail();
        scheduleSave();
    };

    window.removeTravelPlaceFromDay = function removeTravelPlaceFromDay(id) {
        if (sharedView) return;
        state.itinerary[state.trip.activeDay] = activeDayIds().filter(placeId => placeId !== id);
        delete state.scheduleTimes[state.trip.activeDay][id];
        renderAll();
        scheduleSave();
    };

    window.removeTravelCandidate = function removeTravelCandidate(id) {
        if (sharedView) return;
        const place = state.places.find(item => item.id === id);
        if (!place || !window.confirm(`'${place.name}'을 후보와 모든 일정에서 삭제할까요?`)) return;
        state.places = state.places.filter(item => item.id !== id);
        Object.keys(state.itinerary).forEach(day => { state.itinerary[day] = state.itinerary[day].filter(placeId => placeId !== id); });
        Object.keys(state.scheduleTimes || {}).forEach(day => { if (state.scheduleTimes[day]) delete state.scheduleTimes[day][id]; });
        if (selectedPlaceId === id) selectedPlaceId = '';
        renderAll();
        scheduleSave();
    };

    window.updateTravelPlaceNote = function updateTravelPlaceNote(id, value) {
        if (sharedView) return;
        const place = state.places.find(item => item.id === id);
        if (!place) return;
        place.note = String(value || '').slice(0, 500);
        scheduleSave();
    };

    window.openTravelReview = function openTravelReview(id) {
        const place = placeById(id);
        if (!place) return;
        window.open(naverReviewUrl(place), '_blank', 'noopener,noreferrer');
    };

    window.addTravelPlaceManually = function addTravelPlaceManually() {
        if (sharedView) return;
        const name = cleanText(window.prompt('장소 이름을 입력하세요.'), 80);
        if (!name) return;
        const address = cleanText(window.prompt('지역이나 주소를 입력하세요. (선택)'), 160);
        const category = normalizeCategory(window.prompt('분류를 입력하세요. 예: 숙소, 맛집, 카페, 관광') || 'other');
        const place = normalizePlace({ id: uid('manual'), name, address, category, categoryLabel: CATEGORY_META[category].label }, 'manual');
        state.places.unshift(place);
        selectedPlaceId = place.id;
        renderAll();
        scheduleSave();
    };

    async function publishTravelShare() {
        if (sharedView) return window.location.href;
        const response = await fetch('/api/travel/collaboration/invite', {
            method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ board: state, collaborationId: state.collaboration?.id || '', revision: state.collaboration?.revision || 0 })
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || '공동 편집 초대 링크를 만들지 못했습니다.');
        state.collaboration = data.collaboration;
        return data.url;
    }

    window.shareTravelBoard = async function shareTravelBoard() {
        const button = document.getElementById('travel-share-button');
        if (button) button.disabled = true;
        try {
            setSyncStatus(sharedView ? '공유 링크 준비 중' : '공동 편집 초대 생성 중', 'saving');
            const url = await publishTravelShare();
            const shareData = { title: state.trip.title, text: `${state.trip.title} 여행을 함께 계획해요.`, url };
            const restoreStatus = () => setSyncStatus(sharedView ? `${sharedBy}님의 공유 일정 · 읽기 전용` : savedStatusText(), 'saved');
            if (navigator.share) {
                await navigator.share(shareData);
                setSyncStatus('공유 완료', 'saved');
                window.setTimeout(restoreStatus, 1400);
            } else {
                await navigator.clipboard.writeText(url);
                setSyncStatus('공유 링크를 복사했어요', 'saved');
                window.setTimeout(restoreStatus, 1600);
            }
        } catch (error) {
            const restoreStatus = () => setSyncStatus(sharedView ? `${sharedBy}님의 공유 일정 · 읽기 전용` : savedStatusText(), 'saved');
            if (error?.name === 'AbortError') restoreStatus();
            else {
                setSyncStatus(error.message || '공유 링크를 만들지 못했습니다.', 'error');
                window.setTimeout(restoreStatus, 2000);
            }
        } finally {
            if (button) button.disabled = false;
        }
    };

    window.acceptTravelInvite = async function acceptTravelInvite() {
        if (!pendingInviteToken) return;
        const button = document.getElementById('travel-invite-accept');
        if (button) button.disabled = true;
        try {
            const response = await fetch(`/api/travel/invite/${encodeURIComponent(pendingInviteToken)}/accept`, { method: 'POST', credentials: 'same-origin' });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || '공동 여행에 참여하지 못했습니다.');
            window.history.replaceState({ tabName: 'travel' }, '', '/Travel');
            pendingInviteToken = '';
            document.getElementById('travel-invite-panel')?.classList.add('hidden-content');
            await loadBoard();
            window.openTravelTrip(data.tripId);
        } catch (error) {
            setSyncStatus(error.message || '공동 여행에 참여하지 못했습니다.', 'error');
        } finally {
            if (button) button.disabled = false;
        }
    };

    async function refreshActiveCollaboration() {
        if (!state?.collaboration?.id || sharedView || saveTimer || document.hidden) return;
        try {
            const response = await fetch(`/api/travel/collaboration/${encodeURIComponent(state.collaboration.id)}`, { credentials: 'same-origin', cache: 'no-store' });
            const data = await response.json();
            if (!response.ok || !data.ok) return;
            if (Number(data.collaboration?.revision || 0) <= Number(state.collaboration.revision || 0)) return;
            const latest = normalizeBoard({ ...data.board, collaboration: data.collaboration });
            const index = tripCollection.trips.findIndex(board => board.trip.id === state.trip.id);
            if (index >= 0) tripCollection.trips[index] = latest;
            state = latest;
            renderAll();
            setSyncStatus('다른 참여자의 수정사항을 반영했어요', 'saved');
        } catch (_) {}
    }

    window.copyTravelSummary = async function copyTravelSummary() {
        const lines = [`${state.trip.title} · ${state.trip.startDate} ~ ${state.trip.endDate}`];
        for (let day = 0; day < tripDays(); day += 1) {
            lines.push('', `DAY ${day + 1} (${formatDayLabel(day)})`);
            const times = state.scheduleTimes?.[day] || {};
            const ids = (state.itinerary[day] || []).map((id, index) => ({ id, index, time: times[id] || '' })).sort((a, b) => a.time && b.time ? a.time.localeCompare(b.time) || a.index - b.index : a.time ? -1 : b.time ? 1 : a.index - b.index);
            const places = ids.map(item => ({ place: placeById(item.id), time: item.time })).filter(item => item.place);
            lines.push(...(places.length ? places.map((item, index) => `${index + 1}. ${item.time ? item.time + ' ' : ''}${item.place.name}`) : ['아직 일정 없음']));
        }
        try {
            await navigator.clipboard.writeText(lines.join('\n'));
            setSyncStatus('일정이 복사됐어요', 'saved');
            window.setTimeout(() => setSyncStatus(typeof authState !== 'undefined' && authState.loggedIn ? '계정에 저장됨' : '이 기기에 저장', 'saved'), 1400);
        } catch (_) {
            window.prompt('아래 일정을 복사하세요.', lines.join('\n'));
        }
    };

    document.addEventListener('DOMContentLoaded', () => {
        window.addEventListener('focus', () => void refreshActiveCollaboration());
        collaborationRefreshTimer = window.setInterval(() => void refreshActiveCollaboration(), 12000);
    });
})();
