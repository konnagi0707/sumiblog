const DATA_VERSION = String(Date.now());

const TEXT = {
  all: "\u5168\u90e8",
  loading: "\u6b63\u5728\u52a0\u8f7d",
  loadingPosts: "\u6b63\u5728\u52a0\u8f7d\u6587\u7ae0...",
  loadFailed: "\u52a0\u8f7d\u5931\u8d25",
  noPosts: "\u5f53\u524d\u7b5b\u9009\u6761\u4ef6\u4e0b\u6ca1\u6709\u6587\u7ae0\u3002",
  dataLoadFailed: "\u6570\u636e\u52a0\u8f7d\u5931\u8d25\u3002\u8bf7\u5148\u8fd0\u884c\u66f4\u65b0\u811a\u672c\u751f\u6210 data/posts.json\u3002",
  source: "\u67e5\u770b\u5b98\u65b9\u539f\u6587",
  memberUnavailable: "\u6210\u5458\u8d44\u6599\u6682\u65f6\u4e0d\u53ef\u7528\u3002",
  memberName: "\u5bae\u5730 \u3059\u307f\u308c",
  memberAlt: "\u5bae\u5730\u3059\u307f\u308c",
  memberKana: "\u307f\u3084\u3061 \u3059\u307f\u308c",
  supportColors: "\u30d0\u30a4\u30aa\u30ec\u30c3\u30c8 \u00d7 \u30ec\u30c3\u30c9",
  greetingCard: "\u30b0\u30ea\u30fc\u30c6\u30a3\u30f3\u30b0\u30ab\u30fc\u30c9",
  greetingPhoto: "\u30d5\u30a9\u30c8",
  officialProfile: "\u6210\u5458\u5b98\u65b9\u9875",
  greetingList: "\u30b0\u30ea\u30fc\u30c6\u30a3\u30f3\u30b0\u4e00\u89a7",
  profileArchive: "\u516c\u5f0f\u7167\u30a2\u30fc\u30ab\u30a4\u30d6",
  monthlyArchive: "\u6708\u5225\u30a2\u30fc\u30ab\u30a4\u30d6",
};

const state = {
  posts: [],
  filteredPosts: [],
  member: null,
  memberHistory: null,
  meta: null,
  activeId: null,
  activeMonth: "all",
  keyword: "",
  loading: true,
  error: "",
};

const postListEl = document.getElementById("post-list");
const postDetailEl = document.getElementById("post-detail");
const memberPanelEl = document.getElementById("member-panel");
const monthSelectEl = document.getElementById("month-select");
const keywordInputEl = document.getElementById("keyword-input");
const postCountEl = document.getElementById("post-count");
const archiveUpdatedEl = document.getElementById("archive-updated");
const brandAvatarEl = document.getElementById("brand-avatar");
const openFiltersEl = document.getElementById("open-filters");
const openMemberEl = document.getElementById("open-member");
const backdropEl = document.getElementById("drawer-backdrop");

function formatDate(date) {
  if (!date) return "";
  return date.replaceAll("-", ".");
}

function formatUpdatedAt(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

async function fetchJson(path) {
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(`${path}${separator}v=${DATA_VERSION}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${path} HTTP ${response.status}`);
  }
  return response.json();
}

function parseHashId() {
  const raw = window.location.hash.replace("#", "").trim();
  if (!raw) return null;
  const id = Number(raw);
  return Number.isInteger(id) ? id : null;
}

function setHash(id) {
  const hash = `#${id}`;
  if (window.location.hash !== hash) {
    history.replaceState(null, "", hash);
  }
}

function closeDrawers() {
  document.body.classList.remove("drawer-open", "filters-open", "member-open");
}

function openDrawer(kind) {
  closeDrawers();
  document.body.classList.add("drawer-open", kind === "member" ? "member-open" : "filters-open");
}

function renderMonthOptions() {
  const months = [...new Set(state.posts.map((post) => post.date?.slice(0, 7)).filter(Boolean))];
  monthSelectEl.innerHTML = "";

  const allOption = document.createElement("option");
  allOption.value = "all";
  allOption.textContent = TEXT.all;
  monthSelectEl.appendChild(allOption);

  months.forEach((month) => {
    const option = document.createElement("option");
    option.value = month;
    option.textContent = month;
    monthSelectEl.appendChild(option);
  });

  monthSelectEl.value = state.activeMonth;
}

function postSearchText(post) {
  const blocksText = Array.isArray(post.contentBlocks)
    ? post.contentBlocks
        .filter((block) => block?.type === "text")
        .map((block) => block.text || "")
        .join("\n")
    : "";
  return `${post.title || ""}\n${post.content || ""}\n${blocksText}`.toLowerCase();
}

function applyFilters({ preferHash = false } = {}) {
  const keyword = state.keyword.trim().toLowerCase();
  state.filteredPosts = state.posts.filter((post) => {
    const month = post.date?.slice(0, 7) || "";
    if (state.activeMonth !== "all" && month !== state.activeMonth) return false;
    if (!keyword) return true;
    return postSearchText(post).includes(keyword);
  });

  const hashId = preferHash ? parseHashId() : null;
  const visibleIds = new Set(state.filteredPosts.map((post) => post.id));
  if (hashId && visibleIds.has(hashId)) {
    state.activeId = hashId;
  } else if (!state.activeId || !visibleIds.has(state.activeId)) {
    state.activeId = state.filteredPosts[0]?.id || null;
  }

  renderList();
  renderDetail();
  renderStatus();
}

function renderStatus() {
  if (state.loading) {
    postCountEl.textContent = TEXT.loading;
    return;
  }

  if (state.error) {
    postCountEl.textContent = TEXT.loadFailed;
    return;
  }

  postCountEl.textContent = `${state.filteredPosts.length} / ${state.posts.length} \u7bc7`;
  archiveUpdatedEl.textContent = formatUpdatedAt(state.meta?.updatedAt);
}

function renderList() {
  postListEl.innerHTML = "";
  state.filteredPosts.forEach((post) => {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.classList.toggle("active", post.id === state.activeId);

    const time = document.createElement("time");
    time.textContent = post.datetime || formatDate(post.date);

    const title = document.createElement("strong");
    title.textContent = post.title || `blog ${post.id}`;

    button.append(time, title);
    button.addEventListener("click", () => {
      state.activeId = post.id;
      setHash(post.id);
      renderList();
      renderDetail();
      closeDrawers();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    li.appendChild(button);
    postListEl.appendChild(li);
  });
}

function appendTextBlock(container, text) {
  String(text || "")
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean)
    .forEach((paragraphText) => {
      const paragraph = document.createElement("p");
      paragraph.className = "blog-paragraph";
      paragraph.textContent = paragraphText;
      container.appendChild(paragraph);
    });
}

function renderPostBody(post) {
  const body = document.createElement("div");
  body.className = "post-body";

  if (Array.isArray(post.contentBlocks) && post.contentBlocks.length > 0) {
    post.contentBlocks.forEach((block) => {
      if (block?.type === "text" && block.text) {
        appendTextBlock(body, block.text);
      }

      if (block?.type === "image" && block.src) {
        const image = document.createElement("img");
        image.className = "blog-image";
        image.src = block.src;
        image.alt = post.title || `${TEXT.memberAlt} blog image`;
        image.loading = "lazy";
        body.appendChild(image);
      }
    });
  } else {
    appendTextBlock(body, post.content || "");
  }

  return body;
}

function renderDetail() {
  if (state.loading) {
    postDetailEl.innerHTML = `<p class="empty">${TEXT.loadingPosts}</p>`;
    return;
  }

  if (state.error) {
    postDetailEl.innerHTML = `<p class="empty">${state.error}</p>`;
    return;
  }

  const post = state.posts.find((item) => item.id === state.activeId);
  if (!post) {
    postDetailEl.innerHTML = `<p class="empty">${TEXT.noPosts}</p>`;
    return;
  }

  const header = document.createElement("header");
  header.className = "post-header";

  const meta = document.createElement("div");
  meta.className = "post-meta";

  const date = document.createElement("time");
  date.textContent = post.datetime || formatDate(post.date);
  meta.appendChild(date);

  (post.tags || []).forEach((tag) => {
    const tagEl = document.createElement("span");
    tagEl.className = "tag";
    tagEl.textContent = tag;
    meta.appendChild(tagEl);
  });

  if (post.imageCount) {
    const imageCount = document.createElement("span");
    imageCount.className = "tag";
    imageCount.textContent = `${post.imageCount} photos`;
    meta.appendChild(imageCount);
  }

  const title = document.createElement("h1");
  title.textContent = post.title || `blog ${post.id}`;
  header.append(meta, title);

  const body = renderPostBody(post);
  const source = document.createElement("a");
  source.className = "source-link";
  source.href = post.sourceUrl;
  source.target = "_blank";
  source.rel = "noreferrer";
  source.textContent = TEXT.source;
  body.appendChild(source);

  postDetailEl.innerHTML = "";
  postDetailEl.append(header, body);
}

function imageRecordSrc(record) {
  return record && typeof record.src === "string" ? record.src : "";
}

function renderChipRow(items, getLabel, onSelect) {
  const row = document.createElement("div");
  row.className = "member-archive-chip-row";
  const chips = [];

  items.forEach((item, index) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "member-archive-chip";
    chip.textContent = getLabel(item, index);
    chip.setAttribute("aria-pressed", "false");
    chip.addEventListener("click", () => {
      chips.forEach((button) => {
        button.classList.remove("active");
        button.setAttribute("aria-pressed", "false");
      });
      chip.classList.add("active");
      chip.setAttribute("aria-pressed", "true");
      onSelect(item, index);
    });
    chips.push(chip);
    row.appendChild(chip);
  });

  if (chips[0]) {
    chips[0].click();
  }

  return row;
}

function renderProfileArchive(profileImgEl, profileHistory) {
  if (!profileImgEl || !profileHistory.length) return null;

  const section = document.createElement("section");
  section.className = "member-archive-section";

  const header = document.createElement("div");
  header.className = "member-archive-head";

  const title = document.createElement("h3");
  title.textContent = TEXT.profileArchive;

  const count = document.createElement("span");
  count.textContent = String(profileHistory.length);
  header.append(title, count);

  const current = document.createElement("p");
  current.className = "member-archive-current";

  const row = renderChipRow(
    profileHistory,
    (item) => item.label || formatUpdatedAt(item.updatedAt) || "--",
    (item) => {
      const src = imageRecordSrc(item.image);
      if (src) {
        profileImgEl.src = src;
      }
      current.textContent = [item.label, formatUpdatedAt(item.updatedAt)].filter(Boolean).join(" / ");
    },
  );

  section.append(header, current, row);
  return section;
}

function renderGreetingArchive(greetingHistory) {
  if (!greetingHistory.length) return null;

  const section = document.createElement("section");
  section.className = "member-archive-section";

  const header = document.createElement("div");
  header.className = "member-archive-head";

  const title = document.createElement("h3");
  title.textContent = TEXT.monthlyArchive;

  const count = document.createElement("span");
  count.textContent = String(greetingHistory.length);
  header.append(title, count);

  const current = document.createElement("p");
  current.className = "member-archive-current";

  const grid = document.createElement("div");
  grid.className = "greeting-grid greeting-grid-archive";

  const cardFigure = document.createElement("figure");
  const cardImage = document.createElement("img");
  const cardCaption = document.createElement("figcaption");
  cardCaption.textContent = TEXT.greetingCard;
  cardFigure.append(cardImage, cardCaption);

  const photoFigure = document.createElement("figure");
  const photoImage = document.createElement("img");
  const photoCaption = document.createElement("figcaption");
  photoCaption.textContent = TEXT.greetingPhoto;
  photoFigure.append(photoImage, photoCaption);
  grid.append(cardFigure, photoFigure);

  const row = renderChipRow(
    greetingHistory,
    (item) => item.month || "--",
    (item) => {
      const cardSrc = imageRecordSrc(item.greetingCard);
      const photoSrc = imageRecordSrc(item.greetingPhoto);
      cardFigure.hidden = !cardSrc;
      photoFigure.hidden = !photoSrc;
      if (cardSrc) {
        cardImage.src = cardSrc;
        cardImage.alt = TEXT.greetingCard;
      }
      if (photoSrc) {
        photoImage.src = photoSrc;
        photoImage.alt = TEXT.greetingPhoto;
      }
      current.textContent = [item.month, formatUpdatedAt(item.updatedAt)].filter(Boolean).join(" / ");
    },
  );

  section.append(header, current, grid, row);
  return section;
}

function renderMember() {
  if (!state.member) {
    memberPanelEl.innerHTML = `<p class="empty">${TEXT.memberUnavailable}</p>`;
    return;
  }

  const member = state.member;
  const profileSrc = member.images?.profile?.src || "";
  const greetingCardSrc = member.images?.greetingCard?.src || "";
  const greetingPhotoSrc = member.images?.greetingPhoto?.src || "";
  const profileHistory = Array.isArray(state.memberHistory?.profileHistory)
    ? state.memberHistory.profileHistory
    : [];
  const greetingHistory = Array.isArray(state.memberHistory?.greetingHistory)
    ? state.memberHistory.greetingHistory
    : [];

  memberPanelEl.innerHTML = "";
  let profileImgEl = null;
  if (profileSrc) {
    const photo = document.createElement("img");
    photo.className = "member-photo";
    photo.src = profileSrc;
    photo.alt = member.name || TEXT.memberAlt;
    photo.loading = "lazy";
    profileImgEl = photo;
    memberPanelEl.appendChild(photo);
    brandAvatarEl.src = profileSrc;
  }

  const name = document.createElement("h2");
  name.className = "member-name";
  name.textContent = member.name || TEXT.memberName;

  const kana = document.createElement("p");
  kana.className = "member-kana";
  kana.textContent = member.kana || TEXT.memberKana;

  const roman = document.createElement("p");
  roman.className = "member-roman";
  roman.textContent = member.roman || "SUMIRE MIYACHI";

  const colorTag = document.createElement("div");
  colorTag.className = "color-tag";
  colorTag.textContent = TEXT.supportColors;

  memberPanelEl.append(name, kana, roman, colorTag);

  if (Array.isArray(member.attributes)) {
    const list = document.createElement("dl");
    list.className = "member-info";
    member.attributes.forEach((item) => {
      const dt = document.createElement("dt");
      dt.textContent = item.label;
      const dd = document.createElement("dd");
      dd.textContent = item.value;
      list.append(dt, dd);
    });
    memberPanelEl.appendChild(list);
  }

  const profileArchive = renderProfileArchive(profileImgEl, profileHistory);
  if (profileArchive) {
    memberPanelEl.appendChild(profileArchive);
  }

  const greetingArchive = renderGreetingArchive(greetingHistory);
  if (greetingArchive) {
    memberPanelEl.appendChild(greetingArchive);
  } else if (greetingCardSrc || greetingPhotoSrc) {
    const grid = document.createElement("div");
    grid.className = "greeting-grid";
    [
      [TEXT.greetingCard, greetingCardSrc],
      [TEXT.greetingPhoto, greetingPhotoSrc],
    ].forEach(([label, src]) => {
      if (!src) return;
      const figure = document.createElement("figure");
      const image = document.createElement("img");
      const caption = document.createElement("figcaption");
      image.src = src;
      image.alt = label;
      image.loading = "lazy";
      caption.textContent = label;
      figure.append(image, caption);
      grid.appendChild(figure);
    });
    memberPanelEl.appendChild(grid);
  }

  const actions = document.createElement("div");
  actions.className = "member-actions";
  [
    [TEXT.officialProfile, member.sourceUrl],
    [TEXT.greetingList, member.greetingListUrl],
  ].forEach(([label, href]) => {
    if (!href) return;
    const link = document.createElement("a");
    link.href = href;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = label;
    actions.appendChild(link);
  });
  memberPanelEl.appendChild(actions);
}

function initializeEvents() {
  monthSelectEl.addEventListener("change", (event) => {
    state.activeMonth = event.target.value;
    applyFilters();
  });

  keywordInputEl.addEventListener("input", (event) => {
    state.keyword = event.target.value;
    applyFilters();
  });

  openFiltersEl.addEventListener("click", () => openDrawer("filters"));
  openMemberEl.addEventListener("click", () => openDrawer("member"));
  backdropEl.addEventListener("click", closeDrawers);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDrawers();
  });

  window.addEventListener("hashchange", () => applyFilters({ preferHash: true }));
}

async function init() {
  initializeEvents();

  try {
    const [posts, member, memberHistory, meta] = await Promise.all([
      fetchJson("data/posts.json"),
      fetchJson("data/member.json").catch(() => null),
      fetchJson("data/member_history.json").catch(() => null),
      fetchJson("data/archive_meta.json").catch(() => null),
    ]);

    state.posts = [...posts].sort((a, b) => {
      const dateCompare = String(b.date || "").localeCompare(String(a.date || ""));
      if (dateCompare !== 0) return dateCompare;
      return Number(b.id || 0) - Number(a.id || 0);
    });
    state.member = member;
    state.memberHistory = memberHistory;
    state.meta = meta;
    state.loading = false;

    renderMonthOptions();
    renderMember();
    applyFilters({ preferHash: true });
  } catch (error) {
    console.error(error);
    state.loading = false;
    state.error = TEXT.dataLoadFailed;
    renderStatus();
    renderDetail();
  }
}

init();
