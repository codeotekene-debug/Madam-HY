const mobileMenuButton =
    document.getElementById("mobileMenuButton");

const sidebar =
    document.getElementById("sidebar");

const sidebarOverlay =
    document.getElementById("sidebarOverlay");

const sidebarClose =
    document.getElementById("sidebarClose");


function openSidebar() {

    if (!sidebar) return;

    sidebar.classList.add("open");

    sidebarOverlay?.classList.add("active");
}


function closeSidebar() {

    if (!sidebar) return;

    sidebar.classList.remove("open");

    sidebarOverlay?.classList.remove("active");
}


mobileMenuButton?.addEventListener(
    "click",
    openSidebar
);


sidebarOverlay?.addEventListener(
    "click",
    closeSidebar
);


sidebarClose?.addEventListener(
    "click",
    closeSidebar
);
