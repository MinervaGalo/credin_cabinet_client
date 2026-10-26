
document.addEventListener("DOMContentLoaded", () => {
    const dialog = document.getElementById("popupDialog");
    const frame = dialog?.querySelector("iframe");

    document.querySelectorAll("a[data-popup]").forEach((link) => {
        link.addEventListener("click", (event) => {
            if (!dialog || !frame || typeof dialog.showModal !== "function") {
                return;
            }

            event.preventDefault();
            frame.src = link.href;
            dialog.showModal();
        });
    });

    dialog?.addEventListener("click", (event) => {
        if (event.target === dialog) {
            dialog.close();
        }
    });

    document.querySelectorAll("[data-table-search]").forEach((input) => {
        input.addEventListener("input", () => {
            const table = document.getElementById(input.dataset.tableSearch);

            if (!table) {
                return;
            }

            const query = input.value.toLocaleLowerCase("ru");

            table.querySelectorAll("tbody tr").forEach((row) => {
                row.hidden = !row.innerText
                    .toLocaleLowerCase("ru")
                    .includes(query);
            });
        });
    });

    document.querySelectorAll("[data-table-filter]").forEach((select) => {
        select.addEventListener("change", () => {
            const table = document.getElementById(select.dataset.tableFilter);

            if (!table) {
                return;
            }

            const filter = select.value;

            table.querySelectorAll("tbody tr").forEach((row) => {
                row.hidden = Boolean(
                    filter && !row.innerText.includes(filter)
                );
            });
        });
    });
    
    const companySelect = document.getElementById("companySelect");
    const companyName = document.getElementById("companyName");
    const companyMenu = document.getElementById("companyMenu");

    if (companySelect && companyName && companyMenu) {
        companySelect.addEventListener("click", () => {
            const isExpanded =
                companySelect.getAttribute("aria-expanded") === "true";

            companySelect.setAttribute("aria-expanded", String(!isExpanded));
            companyMenu.hidden = isExpanded;
        });

        companyMenu.querySelectorAll("[data-company]").forEach((option) => {
            option.addEventListener("click", () => {
                const selectedCompany = option.dataset.company;

                companyName.textContent = selectedCompany;

                companyMenu
                    .querySelectorAll("[data-company]")
                    .forEach((item) => {
                        const isActive = item === option;

                        item.classList.toggle("active", isActive);

                        if (isActive) {
                            item.setAttribute("aria-current", "true");
                        } else {
                            item.removeAttribute("aria-current");
                        }
                    });

                companyMenu.hidden = true;
                companySelect.setAttribute("aria-expanded", "false");
            });
        });

        document.addEventListener("click", (event) => {
            if (!event.target.closest(".company-switcher")) {
                companyMenu.hidden = true;
                companySelect.setAttribute("aria-expanded", "false");
            }
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                companyMenu.hidden = true;
                companySelect.setAttribute("aria-expanded", "false");
            }
        });
    }

});
