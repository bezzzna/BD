const API_BASE = '/api';

const TABLE_CONFIG = {
    participants: {
        endpoint: '/applications',
        sectionId: 'participants',
        columns: [
            (row, index) => index + 1,
            (row) => row.fio,
            (row) => row.programs,
            (row) => row.birth_date,
            (row) => row.class,
            (row) => row.school,
            (row) => row.city,
            (row) => row.phone,
            (row) => row.phone_parent,
            (row) => row.email,
        ],
    },
    programs: {
        endpoint: '/programs',
        sectionId: 'programs',
        columns: [
            (row, index) => index + 1,
            (row) => row.name,
            (row) => row.category,
            (row) => row.date_start,
            (row) => row.date_end,
            (row) => row.participants_count,
            (row) => row.format,
        ],
    },
    events: {
        endpoint: '/events',
        sectionId: 'events',
        columns: [
            (row, index) => index + 1,
            (row) => row.name,
            (row) => row.event_date,
            (row) => row.program,
            (row) => row.place,
            (row) => row.participants_count,
        ],
    },
};

const buttons = document.querySelectorAll('.buttons button');
const tables = document.querySelectorAll('.bd_table');
const statusEl = document.getElementById('status');
const participantsMetaEl = document.getElementById('participants-meta');
const programsMetaEl = document.getElementById('programs-meta');
const participantsSearchEl = document.getElementById('participants-search');
const participantsProgramSearchEl = document.getElementById('participants-program-search');
const participantsCountFilterEl = document.getElementById('participants-count-filter');
const programsSearchEl = document.getElementById('programs-search');
const programsParticipantSearchEl = document.getElementById('programs-participant-search');
const programsCountFilterEl = document.getElementById('programs-count-filter');

const cache = {};
const state = {
    participantsRaw: [],
    participantsAggregated: [],
    programsRaw: [],
    programsEnriched: [],
};

function setStatus(message, isError = false) {
    statusEl.textContent = message;
    statusEl.classList.toggle('error', isError);
}

function cell(value) {
    return value ?? '—';
}

function normalizeProgramList(row) {
    if (Array.isArray(row.program_list)) {
        return row.program_list.filter(Boolean);
    }
    if (typeof row.programs === 'string' && row.programs.trim()) {
        return row.programs.split(',').map((item) => item.trim()).filter(Boolean);
    }
    return [];
}

function aggregateParticipants(rows) {
    const grouped = new Map();

    rows.forEach((row) => {
        const keyBase = [row.email, row.phone, row.fio].find((item) => item && String(item).trim());
        const key = String(keyBase || row.id);

        if (!grouped.has(key)) {
            grouped.set(key, {
                ...row,
                program_list: [],
            });
        }

        const item = grouped.get(key);
        item.fio = item.fio || row.fio;
        item.birth_date = item.birth_date || row.birth_date;
        item.class = item.class || row.class;
        item.school = item.school || row.school;
        item.city = item.city || row.city;
        item.phone = item.phone || row.phone;
        item.phone_parent = item.phone_parent || row.phone_parent;
        item.email = item.email || row.email;

        const programSet = new Set(item.program_list);
        normalizeProgramList(row).forEach((name) => programSet.add(name));
        item.program_list = Array.from(programSet);
        item.programs = item.program_list.join(', ');
    });

    return Array.from(grouped.values());
}

function buildProgramParticipantsMap(participantsRows) {
    const map = new Map();
    participantsRows.forEach((row) => {
        const fio = row.fio || 'Без имени';
        normalizeProgramList(row).forEach((programName) => {
            if (!map.has(programName)) {
                map.set(programName, new Set());
            }
            map.get(programName).add(fio);
        });
    });
    return map;
}

function enrichProgramsWithParticipants(programRows, programParticipantsMap) {
    return programRows.map((row) => {
        const list = Array.from(programParticipantsMap.get(row.name) || []);
        return {
            ...row,
            participant_list: list,
            participants_count: Math.max(Number(row.participants_count || 0), list.length),
        };
    });
}

function filterParticipants(rows) {
    const query = (participantsSearchEl?.value || '').trim().toLowerCase();
    const programQuery = (participantsProgramSearchEl?.value || '').trim().toLowerCase();
    const minPrograms = Number(participantsCountFilterEl?.value || 1);

    return rows.filter((row) => {
        const programs = normalizeProgramList(row);
        const text = [
            row.fio,
            row.school,
            row.city,
            row.email,
            row.phone,
            row.phone_parent,
            programs.join(' '),
        ].join(' ').toLowerCase();
        const byQuery = !query || text.includes(query);
        const byProgram = !programQuery || programs.some((name) => name.toLowerCase().includes(programQuery));
        const byCount = programs.length >= minPrograms;
        return byQuery && byProgram && byCount;
    });
}

function filterPrograms(rows) {
    const query = (programsSearchEl?.value || '').trim().toLowerCase();
    const participantQuery = (programsParticipantSearchEl?.value || '').trim().toLowerCase();
    const minCount = Number(programsCountFilterEl?.value || 0);

    return rows.filter((row) => {
        const text = [row.name, row.category, row.format].join(' ').toLowerCase();
        const participants = (row.participant_list || []).join(' ').toLowerCase();
        const byQuery = !query || text.includes(query);
        const byParticipant = !participantQuery || participants.includes(participantQuery);
        const byCount = Number(row.participants_count || 0) >= minCount;
        return byQuery && byParticipant && byCount;
    });
}

function renderParticipantsTable(sectionId, rows, config) {
    const tbody = document.querySelector(`#${sectionId} tbody`);
    tbody.innerHTML = '';
    const aggregatedRows = rows;

    if (!aggregatedRows.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = config.columns.length;
        td.className = 'empty';
        td.textContent = 'Нет записей';
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }

    aggregatedRows.forEach((row, index) => {
        const tr = document.createElement('tr');
        config.columns.forEach((getValue, colIndex) => {
            const td = document.createElement('td');
            if (colIndex === 2) {
                const programs = normalizeProgramList(row);
                const primary = programs[0] || '—';
                td.textContent = primary;
                if (programs.length > 1) {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.className = 'expand-programs';
                    button.textContent = `еще ${programs.length - 1}`;
                    button.setAttribute('aria-expanded', 'false');
                    td.appendChild(document.createTextNode(' '));
                    td.appendChild(button);
                }
            } else {
                td.textContent = cell(getValue(row, index));
            }
            tr.appendChild(td);
        });
        tbody.appendChild(tr);

        if (normalizeProgramList(row).length > 1) {
            const detailsRow = document.createElement('tr');
            detailsRow.className = 'program-details-row';
            detailsRow.hidden = true;
            const detailsCell = document.createElement('td');
            detailsCell.colSpan = config.columns.length;
            detailsCell.className = 'program-details-cell';
            const title = document.createElement('div');
            title.className = 'program-details-title';
            title.textContent = 'Все программы участника:';
            detailsCell.appendChild(title);

            const list = document.createElement('ul');
            list.className = 'program-details-list';
            normalizeProgramList(row).forEach((programName) => {
                const li = document.createElement('li');
                li.textContent = programName;
                list.appendChild(li);
            });
            detailsCell.appendChild(list);
            detailsRow.appendChild(detailsCell);
            tbody.appendChild(detailsRow);

            const toggleButton = tr.querySelector('.expand-programs');
            toggleButton.addEventListener('click', () => {
                const isHidden = detailsRow.hidden;
                detailsRow.hidden = !isHidden;
                toggleButton.setAttribute('aria-expanded', String(isHidden));
            });
        }
    });
}

function renderProgramsTable(sectionId, rows, config) {
    const tbody = document.querySelector(`#${sectionId} tbody`);
    tbody.innerHTML = '';

    if (!rows.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = config.columns.length;
        td.className = 'empty';
        td.textContent = 'Нет записей';
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }

    rows.forEach((row, index) => {
        const tr = document.createElement('tr');
        config.columns.forEach((getValue, colIndex) => {
            const td = document.createElement('td');
            if (colIndex === 1) {
                td.textContent = cell(getValue(row, index));
                if ((row.participant_list || []).length > 0) {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.className = 'expand-programs';
                    button.textContent = `участники ${row.participant_list.length}`;
                    button.setAttribute('aria-expanded', 'false');
                    td.appendChild(document.createTextNode(' '));
                    td.appendChild(button);
                }
            } else {
                td.textContent = cell(getValue(row, index));
            }
            tr.appendChild(td);
        });
        tbody.appendChild(tr);

        if ((row.participant_list || []).length > 0) {
            const detailsRow = document.createElement('tr');
            detailsRow.className = 'program-details-row';
            detailsRow.hidden = true;
            const detailsCell = document.createElement('td');
            detailsCell.colSpan = config.columns.length;
            detailsCell.className = 'program-details-cell';

            const title = document.createElement('div');
            title.className = 'program-details-title';
            title.textContent = 'Участники программы:';
            detailsCell.appendChild(title);

            const list = document.createElement('ul');
            list.className = 'program-details-list';
            row.participant_list.forEach((participantName) => {
                const li = document.createElement('li');
                li.textContent = participantName;
                list.appendChild(li);
            });
            detailsCell.appendChild(list);
            detailsRow.appendChild(detailsCell);
            tbody.appendChild(detailsRow);

            const toggleButton = tr.querySelector('.expand-programs');
            toggleButton?.addEventListener('click', () => {
                const isHidden = detailsRow.hidden;
                detailsRow.hidden = !isHidden;
                toggleButton.setAttribute('aria-expanded', String(isHidden));
            });
        }
    });
}

function renderTable(sectionId, rows, config) {
    if (sectionId === 'participants') return renderParticipantsTable(sectionId, rows, config);
    if (sectionId === 'programs') return renderProgramsTable(sectionId, rows, config);

    const tbody = document.querySelector(`#${sectionId} tbody`);
    tbody.innerHTML = '';

    if (!rows.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = config.columns.length;
        td.className = 'empty';
        td.textContent = 'Нет записей';
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }

    rows.forEach((row, index) => {
        const tr = document.createElement('tr');
        config.columns.forEach((getValue) => {
            const td = document.createElement('td');
            td.textContent = cell(getValue(row, index));
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
}

function renderFilteredTables() {
    const participantsFiltered = filterParticipants(state.participantsAggregated);
    const programsFiltered = filterPrograms(state.programsEnriched);

    renderTable('participants', participantsFiltered, TABLE_CONFIG.participants);
    renderTable('programs', programsFiltered, TABLE_CONFIG.programs);
    renderTable('events', cache.events || [], TABLE_CONFIG.events);

    if (participantsMetaEl) {
        participantsMetaEl.textContent = `Показано участников: ${participantsFiltered.length} из ${state.participantsAggregated.length}`;
    }
    if (programsMetaEl) {
        programsMetaEl.textContent = `Показано программ: ${programsFiltered.length} из ${state.programsEnriched.length}`;
    }
}

async function fetchTable(key) {
    if (cache[key]) {
        return cache[key];
    }

    const config = TABLE_CONFIG[key];
    const response = await fetch(`${API_BASE}${config.endpoint}`);

    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || 'Не удалось загрузить данные');
    }

    const data = await response.json();
    cache[key] = data;
    return data;
}

async function loadAllTables() {
    setStatus('Загрузка данных...');
    try {
        const [participants, programs, events] = await Promise.all([
            fetchTable('participants'),
            fetchTable('programs'),
            fetchTable('events'),
        ]);

        state.participantsRaw = participants;
        state.participantsAggregated = aggregateParticipants(participants);
        state.programsRaw = programs;
        state.programsEnriched = enrichProgramsWithParticipants(
            programs,
            buildProgramParticipantsMap(state.participantsAggregated),
        );
        cache.events = events;

        renderFilteredTables();
        setStatus('');
    } catch (error) {
        setStatus(
            `${error.message}. Запустите сервер: python app.py и откройте http://127.0.0.1:5000`,
            true,
        );
    }
}

function bindFilterEvents() {
    [
        participantsSearchEl,
        participantsProgramSearchEl,
        participantsCountFilterEl,
        programsSearchEl,
        programsParticipantSearchEl,
        programsCountFilterEl,
    ].forEach((element) => {
        element?.addEventListener('input', renderFilteredTables);
        element?.addEventListener('change', renderFilteredTables);
    });
}

buttons.forEach((button) => {
    button.addEventListener('click', () => {
        const tableId = button.dataset.table;

        buttons.forEach((btn) => btn.classList.remove('active'));
        button.classList.add('active');

        tables.forEach((table) => {
            table.classList.toggle('active', table.id === tableId);
        });
    });
});

bindFilterEvents();
loadAllTables();
