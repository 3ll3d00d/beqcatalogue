document$.subscribe(function() {
    var tables = document.querySelectorAll("article table:not([class])")
    tables.forEach(function(table) {
        new Tablesort(table);
        var tf = new TableFilter(table, {
            base_path: '',
            ignore_diacritics: true,
        });
        tf.init();
    })
})