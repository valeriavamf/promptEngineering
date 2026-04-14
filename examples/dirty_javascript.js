// notification stuff

var msgs = []
var shown = []
var max = 5
var delay = 3000

function add(t, m, u) {
    if (msgs.length >= max) {
        return
    }
    var id = Date.now() + Math.random()
    msgs.push({id: id, t: t, m: m, u: u, read: false})
}

function show(id) {
    for (var i = 0; i < msgs.length; i++) {
        if (msgs[i].id == id) {
            if (shown.indexOf(id) == -1) {
                shown.push(id)
                var el = document.createElement('div')
                el.id = 'n-' + id
                if (msgs[i].t == 'error') {
                    el.style.background = '#ff4444'
                    el.style.color = '#fff'
                } else if (msgs[i].t == 'warn') {
                    el.style.background = '#ffaa00'
                    el.style.color = '#000'
                } else {
                    el.style.background = '#44bb44'
                    el.style.color = '#fff'
                }
                el.style.padding = '10px'
                el.style.margin = '5px'
                el.style.borderRadius = '4px'
                el.innerText = msgs[i].m
                if (msgs[i].u) {
                    var btn = document.createElement('button')
                    btn.innerText = 'Undo'
                    btn.onclick = function() { msgs[i].u() }
                    el.appendChild(btn)
                }
                document.body.appendChild(el)
                msgs[i].read = true
                setTimeout(function() {
                    var x = document.getElementById('n-' + id)
                    if (x) x.remove()
                }, delay)
            }
        }
    }
}

function dismiss(id) {
    var x = document.getElementById('n-' + id)
    if (x) x.remove()
    var tmp = []
    for (var i = 0; i < msgs.length; i++) {
        if (msgs[i].id != id) tmp.push(msgs[i])
    }
    msgs = tmp
    var tmp2 = []
    for (var i = 0; i < shown.length; i++) {
        if (shown[i] != id) tmp2.push(shown[i])
    }
    shown = tmp2
}

function clear() {
    for (var i = 0; i < msgs.length; i++) {
        var x = document.getElementById('n-' + msgs[i].id)
        if (x) x.remove()
    }
    msgs = []
    shown = []
}

function unread() {
    var c = 0
    for (var i = 0; i < msgs.length; i++) {
        if (!msgs[i].read) c++
    }
    return c
}
