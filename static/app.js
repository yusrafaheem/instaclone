// instaclone frontend -- plain JS, no build step, no framework (npm/pip
// registries aren't reachable in the environment this was built in, so
// there's no React/webpack toolchain available; a hash router plus
// template cloning gets a real multi-page feel without one).

const API = "/api";

function getToken() {
  return localStorage.getItem("instaclone_token");
}

function getUsername() {
  return localStorage.getItem("instaclone_username");
}

function setSession(token, username) {
  localStorage.setItem("instaclone_token", token);
  localStorage.setItem("instaclone_username", username);
}

function clearSession() {
  localStorage.removeItem("instaclone_token");
  localStorage.removeItem("instaclone_username");
}

async function api(path, options = {}) {
  const headers = options.headers || {};
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.json);
  }
  const res = await fetch(API + path, { ...options, headers });
  let data = null;
  try {
    data = await res.json();
  } catch (e) {
    data = null;
  }
  if (!res.ok) {
    const err = new Error((data && data.error) || res.statusText);
    err.status = res.status;
    throw err;
  }
  return data;
}

const app = document.getElementById("app");
const topnav = document.getElementById("topnav");

function renderTopnav() {
  topnav.innerHTML = "";
  if (!getToken()) return;
  const explore = document.createElement("a");
  explore.href = "#/feed";
  explore.textContent = "⌂"; // home glyph
  const upload = document.createElement("a");
  upload.href = "#/upload";
  upload.textContent = "+";
  const profile = document.createElement("a");
  profile.href = "#/profile/" + getUsername();
  profile.textContent = "☺"; // profile glyph
  const logout = document.createElement("button");
  logout.textContent = "Log out";
  logout.onclick = () => {
    clearSession();
    location.hash = "#/";
  };
  topnav.append(explore, upload, profile, logout);
}

// --- router ---

function router() {
  renderTopnav();
  const hash = location.hash || "#/";

  if (!getToken() && hash !== "#/signup") {
    return renderAuth("login");
  }

  if (hash === "#/" || hash === "#/feed") return renderFeed("following");
  if (hash === "#/explore") return renderFeed("explore");
  if (hash === "#/upload") return renderUpload();
  if (hash.startsWith("#/profile/")) return renderProfile(hash.slice("#/profile/".length));
  return renderFeed("following");
}

window.addEventListener("hashchange", router);
window.addEventListener("DOMContentLoaded", router);

// --- auth view ---

function renderAuth(mode) {
  app.innerHTML = "";
  const tpl = document.getElementById("tpl-auth");
  const node = tpl.content.cloneNode(true);
  const tabs = node.querySelectorAll(".auth-tab");
  const emailField = node.querySelector("#auth-email");
  const errorEl = node.querySelector("#auth-error");

  function setMode(m) {
    mode = m;
    tabs.forEach((t) => t.classList.toggle("active", t.dataset.mode === m));
    emailField.style.display = m === "signup" ? "block" : "none";
    emailField.required = m === "signup";
    errorEl.textContent = "";
  }

  tabs.forEach((t) => (t.onclick = () => setMode(t.dataset.mode)));
  setMode(mode);

  node.querySelector("#auth-form").onsubmit = async (e) => {
    e.preventDefault();
    errorEl.textContent = "";
    const username = node.querySelector("#auth-username").value.trim();
    const password = node.querySelector("#auth-password").value;
    const email = node.querySelector("#auth-email").value.trim();
    try {
      const path = mode === "signup" ? "/auth/signup" : "/auth/login";
      const body = mode === "signup" ? { username, email, password } : { username, password };
      const result = await api(path, { method: "POST", json: body });
      setSession(result.token, result.username);
      location.hash = "#/feed";
      router();
    } catch (err) {
      errorEl.textContent = err.message;
    }
  };

  app.appendChild(node);
}

// --- feed view ---

function buildPostCard(post) {
  const tpl = document.getElementById("tpl-post-card");
  const node = tpl.content.cloneNode(true);
  const article = node.querySelector(".post-card");

  const avatarLink = node.querySelector(".post-avatar");
  avatarLink.href = "#/profile/" + post.username;
  const usernameLink = node.querySelector(".post-username");
  usernameLink.href = "#/profile/" + post.username;
  usernameLink.textContent = post.username;

  const img = node.querySelector(".post-image");
  img.src = post.image_url;

  const likeBtn = node.querySelector(".like-btn");
  const likeCountEl = node.querySelector(".like-count");
  likeCountEl.textContent = post.like_count;
  likeBtn.classList.toggle("liked", post.liked_by_viewer);
  likeBtn.onclick = async () => {
    const liked = likeBtn.classList.contains("liked");
    try {
      const result = liked
        ? await api(`/posts/${post.id}/like`, { method: "DELETE" })
        : await api(`/posts/${post.id}/like`, { method: "POST" });
      likeCountEl.textContent = result.like_count;
      likeBtn.classList.toggle("liked", result.liked);
    } catch (err) {
      alert(err.message);
    }
  };

  const captionEl = node.querySelector(".post-caption");
  if (post.caption) {
    const strong = document.createElement("strong");
    strong.textContent = post.username;
    captionEl.append(strong, post.caption);
  } else {
    captionEl.remove();
  }

  const commentForm = node.querySelector(".comment-form");
  commentForm.onsubmit = async (e) => {
    e.preventDefault();
    const input = commentForm.querySelector("input");
    const body = input.value.trim();
    if (!body) return;
    try {
      await api(`/posts/${post.id}/comments`, { method: "POST", json: { body } });
      input.value = "";
      loadComments(post.id, node.querySelector(".post-comments"));
    } catch (err) {
      alert(err.message);
    }
  };

  loadComments(post.id, node.querySelector(".post-comments"));
  return article;
}

async function loadComments(postId, container) {
  try {
    const result = await api(`/posts/${postId}/comments`);
    container.innerHTML = "";
    for (const c of result.comments.slice(-3)) {
      const div = document.createElement("div");
      div.className = "comment";
      const strong = document.createElement("strong");
      strong.textContent = c.username + " ";
      div.append(strong, c.body);
      container.appendChild(div);
    }
  } catch (err) {
    // Non-fatal -- a post still renders fine without its comment preview.
  }
}

let currentFeedMode = "following";
let currentFeedCursor = null;

function renderFeed(mode) {
  currentFeedMode = mode;
  currentFeedCursor = null;
  app.innerHTML = "";
  const tpl = document.getElementById("tpl-feed");
  const node = tpl.content.cloneNode(true);
  const tabs = node.querySelectorAll(".feed-tab");
  tabs.forEach((t) => {
    t.classList.toggle("active", t.dataset.feed === mode);
    t.onclick = () => {
      location.hash = t.dataset.feed === "following" ? "#/feed" : "#/explore";
    };
  });
  app.appendChild(node);

  const list = document.getElementById("post-list");
  const loadMoreBtn = document.getElementById("load-more");
  loadMoreBtn.onclick = () => loadFeedPage(list, loadMoreBtn);
  loadFeedPage(list, loadMoreBtn);
}

async function loadFeedPage(list, loadMoreBtn) {
  const path = currentFeedMode === "following" ? "/feed" : "/feed/explore";
  const qs = currentFeedCursor ? `?cursor=${encodeURIComponent(currentFeedCursor)}` : "";
  loadMoreBtn.disabled = true;
  loadMoreBtn.textContent = "Loading...";
  try {
    const result = await api(path + qs);
    for (const post of result.posts) {
      list.appendChild(buildPostCard(post));
    }
    currentFeedCursor = result.next_cursor;
    loadMoreBtn.style.display = currentFeedCursor ? "block" : "none";
    if (result.posts.length === 0 && !currentFeedCursor && list.children.length === 0) {
      const empty = document.createElement("p");
      empty.textContent =
        currentFeedMode === "following"
          ? "Nobody you follow has posted yet -- try Explore."
          : "No posts yet. Be the first!";
      list.appendChild(empty);
    }
  } finally {
    loadMoreBtn.disabled = false;
    loadMoreBtn.textContent = "Load more";
  }
}

// --- upload view ---

function renderUpload() {
  app.innerHTML = "";
  const tpl = document.getElementById("tpl-upload");
  const node = tpl.content.cloneNode(true);
  const fileInput = node.querySelector("#upload-file");
  const preview = node.querySelector("#upload-preview");
  const errorEl = node.querySelector("#upload-error");

  fileInput.onchange = () => {
    const file = fileInput.files[0];
    if (!file) return;
    preview.src = URL.createObjectURL(file);
    preview.style.display = "block";
  };

  node.querySelector("#upload-form").onsubmit = async (e) => {
    e.preventDefault();
    errorEl.textContent = "";
    const file = fileInput.files[0];
    if (!file) return;
    const caption = node.querySelector("#upload-caption").value;
    const formData = new FormData();
    formData.append("image", file);
    formData.append("caption", caption);
    try {
      const res = await fetch(API + "/posts", {
        method: "POST",
        headers: { Authorization: "Bearer " + getToken() },
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || res.statusText);
      location.hash = "#/profile/" + getUsername();
      router();
    } catch (err) {
      errorEl.textContent = err.message;
    }
  };

  app.appendChild(node);
}

// --- profile view ---

async function renderProfile(username) {
  app.innerHTML = "";
  const tpl = document.getElementById("tpl-profile");
  const node = tpl.content.cloneNode(true);
  app.appendChild(node);

  try {
    const profile = await api(`/users/${encodeURIComponent(username)}`);
    document.querySelector(".profile-username").textContent = profile.username;
    document.querySelector(".stat-posts").textContent = profile.posts.length;
    document.querySelector(".stat-followers").textContent = profile.follower_count;
    document.querySelector(".stat-following").textContent = profile.following_count;
    document.querySelector(".profile-bio").textContent = profile.bio;

    const followBtn = document.querySelector(".follow-btn");
    if (profile.username === getUsername()) {
      followBtn.style.display = "none";
    } else {
      const setFollowState = (following) => {
        followBtn.textContent = following ? "Following" : "Follow";
        followBtn.classList.toggle("following", following);
      };
      setFollowState(profile.is_following);
      followBtn.onclick = async () => {
        const following = followBtn.classList.contains("following");
        const result = following
          ? await api(`/users/${username}/follow`, { method: "DELETE" })
          : await api(`/users/${username}/follow`, { method: "POST" });
        setFollowState(result.following);
      };
    }

    const grid = document.getElementById("profile-grid");
    for (const post of profile.posts) {
      const img = document.createElement("img");
      img.src = post.thumb_url;
      grid.appendChild(img);
    }
  } catch (err) {
    app.innerHTML = `<p>${err.message}</p>`;
  }
}
