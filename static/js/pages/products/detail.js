/**
 * MADAM HY - Product detail interactions.
 * Frontend-only detail display and CTA behaviour.
 */

document.addEventListener("DOMContentLoaded", () => {
    const addButtons = document.querySelectorAll(".btn-primary");
    const stockBadge = document.querySelector(".detail-stock");
    const priceText = document.querySelector(".detail-price-row strong");

    addButtons.forEach(button => {
        button.addEventListener("click", () => {
            if (button.textContent.includes("Add to cart") || button.textContent.includes("Add to basket")) {
                button.textContent = "Added to basket";
                button.disabled = true;

                if (stockBadge) {
                    stockBadge.textContent = "Ready for checkout";
                    stockBadge.classList.remove("status-in-stock");
                    stockBadge.classList.add("status-low-stock");
                }
            }
        });
    });

    if (priceText) {
        priceText.title = "Frontend demo pricing";
    }
});
