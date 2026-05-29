# API документация — СИРИУС.ПРИМОРЬЕ

**Базовый URL:** `https://cms.sirius-prim.ru`  
**Авторизация:** Bearer-токен в заголовке `Authorization: Bearer <token>`  
**Получение токена:** `POST /api/auth/local` → поле `jwt` в ответе

---

## Аутентификация

### POST /api/auth/local
Логин по email и паролю.

```json
Body: { "identifier": "email@example.com", "password": "пароль" }
Response: { "jwt": "...", "user": { "id", "documentId", "username", "email", "role" } }
```

### GET /api/users/me
Данные текущего пользователя (требует Bearer-токен).

```
Response: { "id", "documentId", "username", "email", "role": { "name": "Authenticated|Expert|Moderator|Zam" } }
```

---

## Заявки (`/api/applications`)

### Структура объекта Application

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | integer | Числовой ID |
| `documentId` | string | UUID для операций PUT/DELETE |
| `applicationStatus` | enum | `pending` / `approved` / `rejected` / `absent` |
| `confirmationStatus` | enum | `pending` / `confirmed` / `declined` |
| `confirmationComment` | text | Причина отказа от участия (при declined) |
| `formData` | json | Ответы участника на поля формы программы |
| `snapshotName` | string | ФИО участника на момент подачи |
| `snapshotEmail` | email | Email участника |
| `snapshotPhone` | string | Телефон |
| `snapshotSnils` | string | СНИЛС |
| `snapshotPfdo` | string | Номер сертификата ПФДО |
| `snapshotBirthDate` | date | Дата рождения |
| `snapshotCity` | string | Город |
| `parentName` | string | ФИО родителя/опекуна |
| `parentPhone` | string | Телефон родителя |
| `parentEmail` | email | Email родителя |
| `school` | string | Школа |
| `schoolAddress` | string | Адрес школы |
| `grade` | integer | Класс |
| `achievements` | text | Достижения и мотивация |
| `reviewNotes` | text | Комментарий эксперта/модератора |
| `program` | relation | Программа (см. Program) |
| `applicant` | relation | Пользователь-участник |
| `files` | media[] | Прикреплённые файлы |

### GET /api/applications
Список всех заявок (требует авторизации).

```
Query params:
  populate=*                                   — включить все связи
  filters[program][documentId][$eq]=X          — заявки по программе
  filters[applicationStatus][$eq]=approved     — фильтр по статусу
  pagination[pageSize]=25                      — кол-во записей
  pagination[page]=1                           — страница
```

### GET /api/my-applications *(кастомный)*
Заявки **текущего авторизованного пользователя**. Возвращает массив с populate программы, участника и файлов.

```
Response: { "data": [ ...Application[] ] }
```

### POST /api/applications
Создать заявку. Запрещает дублирование (одна заявка от одного участника на одну программу).

```json
Body: {
  "data": {
    "program": "documentId программы",
    "applicant": "documentId пользователя",
    "applicationStatus": "pending",
    "formData": { "ключ": "значение" },
    "snapshotName": "Иванов Иван Иванович",
    "snapshotEmail": "ivan@example.com",
    "snapshotPhone": "+7...",
    "parentName": "...",
    "school": "..."
  }
}
```

### PUT /api/applications/:documentId
Обновить заявку. Используется для смены `applicationStatus`.

```json
Body: { "data": { "applicationStatus": "approved", "reviewNotes": "Комментарий" } }
```

> При смене статуса на `approved` или `rejected` — автоматически отправляется email участнику.

### POST /api/applications/confirm-participation *(кастомный)*
Участник подтверждает или отказывается от участия после одобрения заявки.

```json
Body: {
  "decisions": [
    { "documentId": "uuid заявки", "decision": "confirmed" },
    { "documentId": "uuid заявки", "decision": "declined", "comment": "Причина" }
  ]
}
Response: { "success": true, "processed": 2 }
```

> Отправляет email уведомление по каждому решению.

---

## Программы (`/api/programs`)

### Структура объекта Program

| Поле | Тип | Описание |
|------|-----|----------|
| `title` | string | Название программы |
| `slug` | uid | URL-идентификатор |
| `description` | text | Краткое описание |
| `content` | richtext | Подробное описание (HTML) |
| `category` | enum | `Наука` / `Искусство` / `ВСОШ` / `Спорт` / `Дополнительные общеразвивающие программы` / `Международная деятельность` |
| `subcategory` | enum | Олимпиады, ОЗШ, Дистанционные, Очные и др. |
| `duration` | string | Длительность (напр. «14 дней») |
| `ageGroup` | string | Возраст (напр. «14–17 лет») |
| `startDate` | date | Дата начала |
| `endDate` | date | Дата окончания |
| `maxParticipants` | integer | Максимум участников |
| `registrationOpen` | boolean | Приём заявок открыт |
| `featured` | boolean | Показывать в избранном |
| `formSchema` | json | Схема формы заявки (массив полей) |
| `linkButtons` | json | Кнопки-ссылки (id, text, url, activateAt, deactivateAt) |
| `experts` | relation[] | Назначенные эксперты |
| `applications` | relation[] | Заявки участников |
| `pfdoEventId` | integer | ID в системе ПФДО |
| `municipalityId` | integer | ID муниципалитета (ПФДО) |
| `municipalityName` | string | Название муниципалитета |

### GET /api/programs
```
Query params:
  populate=*
  filters[category][$eq]=Наука
  filters[registrationOpen][$eq]=true
  sort=startDate:asc
  pagination[pageSize]=10
```

### GET /api/programs/:documentId
Одна программа с populate.

### PUT /api/programs/:documentId
Обновить программу (эксперт/модератор).

---

## Роль пользователя

### GET /api/user-role
Получить роль текущего пользователя.

```
Response: { "role": { "id", "name", "type" } }
```

### GET /api/user-role?mode=experts
Получить список экспертов.

- Для роли `Zam` — возвращает только назначенных ему экспертов
- Для остальных — всех экспертов системы

```
Response: [ { "id", "documentId", "username", "email", "firstName", "lastName" } ]
```

---

## Документы пользователей (`/api/documents`)

| Поле | Тип | Описание |
|------|-----|----------|
| `name` | string | Название документа |
| `type` | enum | `certificate` / `portfolio` / `achievement` / `other` |
| `file` | media | Файл |
| `owner` | relation | Владелец (пользователь) |
| `relatedApplication` | relation | Связанная заявка |
| `description` | text | Описание |

### GET /api/documents
```
filters[owner][id][$eq]=123        — документы конкретного участника
filters[type][$eq]=certificate     — только сертификаты
populate=*
```

---

## Нормативные документы сайта (`/api/site-documents`)

Публичный доступ (без токена).

| Поле | Тип | Описание |
|------|-----|----------|
| `title` | string | Название |
| `section` | enum | `federal` / `regional` / `legal` / `reports` |
| `file` | media | PDF-файл (если загружен) |
| `externalUrl` | string | Внешняя ссылка (если нет файла) |
| `order` | integer | Порядок в разделе |

```
GET /api/site-documents?filters[section][$eq]=federal&sort=order:asc
```

---

## Информационные страницы (`/api/info-pages`)

Публичный доступ (без токена).

| Поле | Тип | Описание |
|------|-----|----------|
| `title` | string | Заголовок |
| `slug` | uid | URL: `/info/{slug}` |
| `content` | richtext | Основной контент |
| `sidebar` | richtext | Правый сайдбар |
| `heroImage` | media | Изображение в шапке |
| `documents` | json | Документы `[{title, url, size}]` |
| `linkButtons` | json | Кнопки-ссылки |
| `parent` | relation | Родительская страница |
| `children` | relation[] | Дочерние страницы |

```
GET /api/info-pages?filters[slug][$eq]=vsosh&populate=*
```

---

## Роли в системе

| Роль | `role.name` | Описание |
|------|------------|----------|
| Участник | `Authenticated` | Подаёт заявки, видит свои документы |
| Эксперт | `Expert` | Создаёт программы, рассматривает заявки |
| Зам. директора | `Zam` | Видит программы и заявки своих экспертов |
| Модератор | `Moderator` | Полное управление всем |
| Публичный | `Public` | Только публичное чтение |

---

## Типовые запросы

**Получить все одобренные заявки на программу:**
```
GET /api/applications?filters[program][documentId][$eq]=<id>&filters[applicationStatus][$eq]=approved&populate[applicant]=true&populate[files]=true
```

**Получить участников, подтвердивших участие:**
```
GET /api/applications?filters[confirmationStatus][$eq]=confirmed&populate[applicant]=true&populate[program]=true
```

**Получить участников, отказавшихся от участия:**
```
GET /api/applications?filters[confirmationStatus][$eq]=declined&populate[applicant]=true&populate[program]=true
```

**Получить все заявки участника по email:**
```
GET /api/applications?filters[snapshotEmail][$eq]=ivan@example.com&populate=*
```

**Получить список участников программы с их данными:**
```
GET /api/applications?filters[program][slug][$eq]=название-программы&filters[applicationStatus][$eq]=approved&populate[applicant][populate]=*&populate[files]=true&pagination[pageSize]=100
```
