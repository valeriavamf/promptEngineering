/**
 * @fileoverview In-browser notification manager.
 *
 * Chain-of-Thought refactoring highlights:
 * - Step 2 (SRP): global functions mixed DOM rendering, state mutation, and
 *   timing — split into pure state helpers and a NotificationRenderer class.
 * - Step 2 (DIP): DOM operations are isolated in NotificationRenderer so that
 *   state logic (NotificationStore) has no browser dependency and is testable
 *   in isolation.
 * - Step 4 (smells): magic colour strings and numeric literals extracted to
 *   named constants (STYLES, MAX_QUEUE_SIZE, AUTO_DISMISS_MS).
 * - Step 3 (naming): single-letter params (t, m, u) → (type, message,
 *   onUndo); ambiguous identifiers (msgs, shown) → (queue, displayedIds).
 * - Step 4 (duplicated logic): two nearly identical filter loops inside
 *   dismiss() collapsed into _removeFromArray().
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Maximum number of notifications that can be queued at once. */
const MAX_QUEUE_SIZE = 5;

/** Time in milliseconds before a rendered notification is auto-removed. */
const AUTO_DISMISS_MS = 3000;

/**
 * Inline styles applied to notification elements by severity type.
 *
 * @type {Record<string, {background: string, color: string}>}
 */
const STYLES = {
  error: { background: "#ff4444", color: "#fff" },
  warn:  { background: "#ffaa00", color: "#000" },
  info:  { background: "#44bb44", color: "#fff" },
};

// ---------------------------------------------------------------------------
// Types (JSDoc)
// ---------------------------------------------------------------------------

/**
 * @typedef {'error' | 'warn' | 'info'} NotificationType
 */

/**
 * @typedef {Object} Notification
 * @property {number}          id      - Unique numeric identifier.
 * @property {NotificationType} type   - Visual severity of the notification.
 * @property {string}          message - Human-readable body text.
 * @property {Function|null}   onUndo  - Optional callback shown as an Undo button.
 * @property {boolean}         read    - True once the notification has been displayed.
 */

// ---------------------------------------------------------------------------
// State helpers (pure — no DOM access)
// ---------------------------------------------------------------------------

/**
 * Return a new array with the first element matching {@link predicate} removed.
 *
 * @template T
 * @param {T[]}            array     - Source array (not mutated).
 * @param {function(T): boolean} predicate - Returns true for the item to remove.
 * @returns {T[]} New array without the first matched element.
 */
function _removeWhere(array, predicate) {
  const index = array.findIndex(predicate);
  if (index === -1) return array;
  return [...array.slice(0, index), ...array.slice(index + 1)];
}

/**
 * Generate a collision-resistant numeric ID.
 *
 * @returns {number} A value derived from the current timestamp and a random
 *   component, suitable for use as a short-lived local identifier.
 */
function _generateId() {
  return Date.now() + Math.random();
}

// ---------------------------------------------------------------------------
// NotificationStore — manages queue state, no DOM knowledge
// ---------------------------------------------------------------------------

/**
 * Manages the in-memory queue of pending and active notifications.
 */
class NotificationStore {
  constructor() {
    /** @type {Notification[]} */
    this._queue = [];

    /** @type {number[]} IDs of notifications currently rendered in the DOM. */
    this._displayedIds = [];
  }

  /**
   * Enqueue a new notification if the queue has not reached capacity.
   *
   * @param {NotificationType} type    - Visual severity level.
   * @param {string}           message - Text to display.
   * @param {Function|null}    onUndo  - Optional undo callback.
   * @returns {Notification|null} The created notification, or null when the
   *   queue is full.
   */
  enqueue(type, message, onUndo = null) {
    if (this._queue.length >= MAX_QUEUE_SIZE) return null;

    const notification = { id: _generateId(), type, message, onUndo, read: false };
    this._queue = [...this._queue, notification];
    return notification;
  }

  /**
   * Mark a notification as read and record it as displayed.
   *
   * @param {number} id - ID of the notification to mark.
   * @returns {Notification|undefined} The updated notification, or undefined
   *   if no match is found.
   */
  markDisplayed(id) {
    const notification = this._queue.find((n) => n.id === id);
    if (!notification || this._displayedIds.includes(id)) return undefined;

    notification.read = true;
    this._displayedIds = [...this._displayedIds, id];
    return notification;
  }

  /**
   * Remove a notification from the queue and the displayed-ID set.
   *
   * @param {number} id - ID of the notification to remove.
   */
  remove(id) {
    this._queue = _removeWhere(this._queue, (n) => n.id === id);
    this._displayedIds = _removeWhere(this._displayedIds, (n) => n === id);
  }

  /** Remove all notifications from state. */
  clear() {
    this._queue = [];
    this._displayedIds = [];
  }

  /**
   * Count notifications that have not yet been displayed.
   *
   * @returns {number} Number of unread (undisplayed) notifications.
   */
  unreadCount() {
    return this._queue.filter((n) => !n.read).length;
  }

  /** @returns {Notification[]} Shallow copy of the current queue. */
  getAll() {
    return [...this._queue];
  }
}

// ---------------------------------------------------------------------------
// NotificationRenderer — manages DOM, delegates state to NotificationStore
// ---------------------------------------------------------------------------

/**
 * Renders notification elements to the DOM and wires up auto-dismiss timers.
 *
 * Depends on {@link NotificationStore} for state — never modifies state itself.
 */
class NotificationRenderer {
  /**
   * @param {NotificationStore} store       - Shared state store.
   * @param {HTMLElement}       [container] - Mount point (defaults to document.body).
   */
  constructor(store, container = document.body) {
    this._store = store;
    this._container = container;
  }

  /**
   * Render a notification to the DOM if it has not already been displayed.
   *
   * Starts the auto-dismiss timer upon first render.
   *
   * @param {number} id - ID of the notification to display.
   * @returns {void}
   */
  show(id) {
    const notification = this._store.markDisplayed(id);
    if (!notification) return;

    const element = this._createElement(notification);
    this._container.appendChild(element);

    setTimeout(() => this._removeDomElement(id), AUTO_DISMISS_MS);
  }

  /**
   * Remove a notification from the DOM immediately.
   *
   * @param {number} id - ID of the notification to dismiss.
   * @returns {void}
   */
  dismiss(id) {
    this._removeDomElement(id);
    this._store.remove(id);
  }

  /**
   * Remove all notification elements from the DOM and reset state.
   *
   * @returns {void}
   */
  clearAll() {
    this._store.getAll().forEach(({ id }) => this._removeDomElement(id));
    this._store.clear();
  }

  /**
   * Build a styled DOM element for a notification.
   *
   * @private
   * @param {Notification} notification - The notification to render.
   * @returns {HTMLElement} A fully-constructed, unstyled-but-ready div.
   */
  _createElement(notification) {
    const { id, type, message, onUndo } = notification;
    const style = STYLES[type] ?? STYLES.info;

    const element = document.createElement("div");
    element.id = `notification-${id}`;
    Object.assign(element.style, {
      background: style.background,
      color: style.color,
      padding: "10px",
      margin: "5px",
      borderRadius: "4px",
    });
    element.textContent = message;

    if (typeof onUndo === "function") {
      const undoButton = document.createElement("button");
      undoButton.textContent = "Undo";
      undoButton.addEventListener("click", onUndo);
      element.appendChild(undoButton);
    }

    return element;
  }

  /**
   * Remove a notification's DOM element if it exists.
   *
   * @private
   * @param {number} id - ID whose element should be removed.
   */
  _removeDomElement(id) {
    document.getElementById(`notification-${id}`)?.remove();
  }
}

export { NotificationStore, NotificationRenderer, MAX_QUEUE_SIZE, AUTO_DISMISS_MS };
