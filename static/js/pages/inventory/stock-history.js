/**
 * MADAM HY - Stock history interactions.
 * Frontend-only movement log for stock adjustments and receiving activity.
 */

const stockHistoryData = [
    {
        date: "2026-08-12",
        product: "Green Ankara Fabric Premium",
        category: "Fashion",
        movement: "+24",
        reason: "New delivery",
        staff: "Aisha"
    },
    {
        date: "2026-08-10",
        product: "Wireless Speaker Mini",
        category: "Electronics",
        movement: "-3",
        reason: "Point-of-sale sale",
        staff: "Tunde"
    },
    {
        date: "2026-08-08",
        product: "Kitchen Storage Basket",
        category: "Home",
        movement: "-5",
        reason: "Stock adjustment",
        staff: "Grace"
    },
    {
        date: "2026-08-05",
        product: "Radiant Glow Serum",
        category: "Beauty",
        movement: "+12",
        reason: "Restock",
        staff: "Mary"
    }
];

document.addEventListener("DOMContentLoaded", () => {
    renderStockHistory();
});

function renderStockHistory() {
    const tableBody = document.getElementById("stockHistoryTableBody");

    if (!tableBody) return;

    tableBody.innerHTML = stockHistoryData.map(item => {
        const movementClass = item.movement.starts("+") ? "movement-in" : item.movement.starts("-") ? "movement-out" : "movement-adjustment";

        return `
            <tr>
                <td data-label="Date">${formatDate(item.date)}</td>
                <td data-label="Product"><strong>${item.product}</strong></td>
                <td data-label="Category">${item.category}</td>
                <td data-label="Movement"><span class="movement-pill ${movementClass}">${item.movement}</span></td>
                <td data-label="Reason">${item.reason}</td>
                <td data-label="Staff">${item.staff}</td>
            </tr>
        `;
    }).join("");
}

function formatDate(value) {
    const date = new Date(value + "T00:00:00");
    return date.toLocaleDateString("en-NG", {
        day: "2-digit",
        month: "short",
        year: "numeric"
    });
}
