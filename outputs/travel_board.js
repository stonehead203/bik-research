(function () {
    'use strict';

    const STORAGE_KEY = 'bik-travel-board-v1';
    const CATEGORY_META = {
        all: { label: '전체', icon: '✦' },
        stay: { label: '숙소', icon: '⌂' },
        food: { label: '맛집', icon: '♨' },
        cafe: { label: '카페', icon: '☕' },
        sight: { label: '관광', icon: '◈' },
        shop: { label: '쇼핑', icon: '◇' },
        other: { label: '기타', icon: '·' }
    };

    let state = null;
    let searchResults = [];
    let selectedPlaceId = '';
    let activeCategory = 'all';
    let activeMobilePanel = 'places';
    let saveTimer = 0;
    let initialized = false;
    let lastLoadedUser = '';

    function uid(prefix) {
        return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    }

    function dateString(date) {
        return date.toISOString().slice(0, 10);
    }

    function addDays(value, amount) {
        const date = new Date(`${value}T12:00:00`);
        date.setDate(date.getDate() + amount);
        return dateString(date);
    }

    function defaultBoard() {
        const start = addDays(dateString(new Date()), 30);
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
            itinerary: { 0: [], 1: [], 2: [] }
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
            itinerary: {}
        };
        const ids = new Set(result.places.map(place => place.id));
        const sourceItinerary = input.itinerary && typeof input.itinerary === 'object' ? input.itinerary : {};
        Object.entries(sourceItinerary).slice(0, 31).forEach(([day, values]) => {
            result.itinerary[String(Math.max(0, Number(day) || 0))] = Array.isArray(values)
                ? [...new Set(values.map(String).filter(id => ids.has(id)))].slice(0, 30)
                : [];
        });
        ensureDayBuckets(result);
        return result;
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
        }
        board.trip.activeDay = Math.min(Math.max(0, board.trip.activeDay || 0), days - 1);
    }

    function localLoad() {
        try {
            return normalizeBoard(JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null'));
        } catch (_) {
            return defaultBoard();
        }
    }

    function setSyncStatus(text, type = '') {
        const target = document.getElementById('travel-sync-state');
        if (!target) return;
        target.textContent = text;
        target.className = `travel-sync-state${type ? ` is-${type}` : ''}`;
    }

    async function loadBoard() {
        const loggedIn = typeof authState !== 'undefined' && Boolean(authState.loggedIn);
        const user = loggedIn ? String(authState.loginId || authState.username || '') : '';
        if (!loggedIn) {
            state = localLoad();
            lastLoadedUser = '';
            setSyncStatus('이 기기에 저장', 'saved');
            renderAll();
            return;
        }
        setSyncStatus('여행 보드 불러오는 중', 'saving');
        try {
            const response = await fetch('/api/travel/board', { credentials: 'same-origin', cache: 'no-store' });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || 'load failed');
            const remote = data.board ? normalizeBoard(data.board) : null;
            const local = localLoad();
            state = remote || local;
            lastLoadedUser = user;
            if (!remote && local.places.length) scheduleSave(true);
            setSyncStatus('계정에 저장됨', 'saved');
        } catch (error) {
            state = localLoad();
            setSyncStatus('로컬 저장 모드', 'error');
        }
        renderAll();
    }

    async function saveBoardNow() {
        if (!state) return;
        state.trip.updatedAt = new Date().toISOString();
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        const loggedIn = typeof authState !== 'undefined' && Boolean(authState.loggedIn);
        if (!loggedIn) {
            setSyncStatus('이 기기에 저장', 'saved');
            return;
        }
        setSyncStatus('저장 중', 'saving');
        try {
            const response = await fetch('/api/travel/board', {
                method: 'PUT',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(state)
            });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || 'save failed');
            setSyncStatus('계정에 저장됨', 'saved');
        } catch (_) {
            setSyncStatus('로컬에는 저장됨', 'error');
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
        const places = activeDayIds().map(placeById).filter(Boolean);
        target.ondragover = event => event.preventDefault();
        target.ondrop = event => {
            event.preventDefault();
            const id = event.dataTransfer?.getData('text/travel-place');
            if (id) addTravelPlaceToDay(id);
        };
        if (!places.length) {
            target.innerHTML = '<div class="travel-empty"><div><strong>아직 일정이 비어 있어요</strong>장소 카드의 + 버튼을 누르거나<br>여기로 끌어다 놓으세요.</div></div>';
            return;
        }
        target.innerHTML = places.map((place, index) => `
            <article class="travel-slot" data-index="${index + 1}" draggable="true" data-place-id="${escapeHtml(place.id)}">
                <strong>${escapeHtml(place.name)}</strong>
                <span>${escapeHtml(place.address || place.categoryLabel)}</span>
                <button type="button" class="travel-slot-remove" aria-label="일정에서 제거" onclick="removeTravelPlaceFromDay('${escapeHtml(place.id)}')">×</button>
            </article>`).join('');
        target.querySelectorAll('[draggable="true"]').forEach(card => {
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
                    ${isSearchResult && !saved ? `<button type="button" class="travel-card-button" title="후보에 저장" onclick="event.stopPropagation();saveTravelCandidate('${escapeHtml(place.id)}')">♡</button>` : ''}
                    ${saved ? `<button type="button" class="travel-card-button is-add" title="현재 날짜에 추가" onclick="event.stopPropagation();addTravelPlaceToDay('${escapeHtml(place.id)}')">+</button>` : ''}
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

    function renderMap() {
        const target = document.getElementById('travel-map-canvas');
        if (!target) return;
        const ordered = activeDayIds().map(placeById).filter(Boolean);
        const base = ordered.length ? ordered : state.places;
        target.querySelectorAll('.travel-map-marker,.travel-map-route,.travel-map-empty').forEach(node => node.remove());
        if (!base.length) {
            target.insertAdjacentHTML('beforeend', '<div class="travel-map-empty">장소를 저장하면 이곳에서<br>하루 동선을 한눈에 볼 수 있어요.</div>');
            return;
        }
        const points = base.map((place, index) => mapPoint(place, index, base));
        if (ordered.length > 1) {
            points.slice(0, -1).forEach((point, index) => {
                const next = points[index + 1];
                const dx = next.x - point.x, dy = next.y - point.y;
                const distance = Math.sqrt(dx * dx + dy * dy);
                target.insertAdjacentHTML('beforeend', `<span class="travel-map-route" style="left:${point.x}%;top:${point.y}%;width:${distance}%;transform:rotate(${Math.atan2(dy, dx) * 180 / Math.PI}deg)"></span>`);
            });
        }
        base.forEach((place, index) => {
            const point = points[index];
            target.insertAdjacentHTML('beforeend', `<button type="button" class="travel-map-marker${selectedPlaceId === place.id ? ' active' : ''}" style="left:${point.x}%;top:${point.y}%" onclick="selectTravelPlace('${escapeHtml(place.id)}')" aria-label="${escapeHtml(place.name)}"><span>${index + 1}</span></button>`);
        });
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
        target.innerHTML = `
            <span class="travel-detail-category">${escapeHtml(place.categoryLabel || meta.label)}</span>
            <h3>${escapeHtml(place.name)}</h3>
            <p class="travel-detail-address">${escapeHtml(place.address || '주소 정보가 없습니다.')}</p>
            <div class="travel-detail-actions">
                ${saved
                    ? `<button type="button" class="travel-primary-button" onclick="addTravelPlaceToDay('${escapeHtml(place.id)}')">DAY ${state.trip.activeDay + 1}에 추가</button>`
                    : `<button type="button" class="travel-primary-button" onclick="saveTravelCandidate('${escapeHtml(place.id)}')">후보로 저장</button>`}
                <button type="button" class="travel-quiet-button" onclick="openTravelReview('${escapeHtml(place.id)}')">네이버 후기 보기 ↗</button>
            </div>
            ${saved ? `
                <label class="travel-note-label" for="travel-place-note">내 메모</label>
                <textarea id="travel-place-note" class="travel-note-input" maxlength="500" placeholder="예약 포인트, 먹고 싶은 메뉴, 동행자 의견을 적어두세요." oninput="updateTravelPlaceNote('${escapeHtml(place.id)}', this.value)">${escapeHtml(place.note || '')}</textarea>
                <button type="button" class="travel-quiet-button" style="width:100%;margin-top:7px" onclick="removeTravelCandidate('${escapeHtml(place.id)}')">후보에서 삭제</button>` : ''}
            <p class="travel-source-note">네이버 공식 지역검색은 장소 정보만 제공합니다. 방문자 리뷰 전문은 복제하지 않고 네이버 검색에서 확인하도록 연결합니다.</p>`;
    }

    function renderMobilePanels() {
        document.querySelectorAll('.travel-column').forEach(column => column.classList.toggle('mobile-active', column.dataset.mobilePanel === activeMobilePanel));
        document.querySelectorAll('[data-travel-mobile-tab]').forEach(button => button.classList.toggle('active', button.dataset.travelMobileTab === activeMobilePanel));
    }

    function renderAll() {
        if (!state) return;
        ensureDayBuckets();
        renderTripFields();
        renderDayStrip();
        renderItinerary();
        renderCandidates();
        renderMap();
        renderDetail();
        renderMobilePanels();
    }

    async function searchPlaces(event) {
        event?.preventDefault?.();
        const input = document.getElementById('travel-search-input');
        const meta = document.getElementById('travel-search-meta');
        const query = cleanText(input?.value, 100);
        if (!query) {
            input?.focus();
            return;
        }
        if (meta) meta.textContent = '장소를 찾는 중...';
        const button = document.getElementById('travel-search-button');
        if (button) button.disabled = true;
        try {
            const response = await fetch(`/api/travel/places?q=${encodeURIComponent(query)}`, { cache: 'no-store' });
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
        const user = typeof authState !== 'undefined' && authState.loggedIn ? String(authState.loginId || authState.username || '') : '';
        if (initialized && !force && user === lastLoadedUser) {
            renderAll();
            return;
        }
        initialized = true;
        await loadBoard();
    };

    window.searchTravelPlaces = searchPlaces;

    window.updateTravelTrip = function updateTravelTrip(field, value) {
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
        scheduleSave();
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

    window.removeTravelPlaceFromDay = function removeTravelPlaceFromDay(id) {
        state.itinerary[state.trip.activeDay] = activeDayIds().filter(placeId => placeId !== id);
        renderAll();
        scheduleSave();
    };

    window.removeTravelCandidate = function removeTravelCandidate(id) {
        const place = state.places.find(item => item.id === id);
        if (!place || !window.confirm(`'${place.name}'을 후보와 모든 일정에서 삭제할까요?`)) return;
        state.places = state.places.filter(item => item.id !== id);
        Object.keys(state.itinerary).forEach(day => { state.itinerary[day] = state.itinerary[day].filter(placeId => placeId !== id); });
        if (selectedPlaceId === id) selectedPlaceId = '';
        renderAll();
        scheduleSave();
    };

    window.updateTravelPlaceNote = function updateTravelPlaceNote(id, value) {
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

    window.copyTravelSummary = async function copyTravelSummary() {
        const lines = [`${state.trip.title} · ${state.trip.startDate} ~ ${state.trip.endDate}`];
        for (let day = 0; day < tripDays(); day += 1) {
            lines.push('', `DAY ${day + 1} (${formatDayLabel(day)})`);
            const places = (state.itinerary[day] || []).map(placeById).filter(Boolean);
            lines.push(...(places.length ? places.map((place, index) => `${index + 1}. ${place.name}`) : ['아직 일정 없음']));
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
        const path = window.location.pathname.toLowerCase();
        if (path === '/travel' || !document.getElementById('content-travel')?.classList.contains('hidden-content')) {
            void window.initTravelBoard();
        }
    });
})();
