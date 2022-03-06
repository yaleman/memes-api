
const app = Vue.createApp({
    delimiters: ['|', '|'], // because we use jinja2 for templating
    data: function(){
        return {
        images : [],
        search: '',
        }
    },
    created () {
        let qp = new URLSearchParams(window.location.search);
        if (qp.get("search") != "" && qp.get("q") != null ) {
            this.search = qp.get("q");
        }
        this.getImages();
    },
    computed: {
        filteredImages() {

            return this.images.filter(image =>{
                const searchTerm = this.search.toLowerCase();
                if (searchTerm == ""){
                    return true
                }
                const image_lower = image.toString().toLowerCase();
                let foundit = true;
                searchTerm.split(" ").forEach(term => {
                    if ( image_lower.includes(term) == false ) {
                        foundit = false;
                    }
                })
                return foundit

            })
        },
        count_filteredImages() {
            return this.filteredImages.length;
        },
        totalImages() {
            return this.images.length;
        }
    },
    methods: {
        getImages: function() {
            axios.get(
                "/allimages",
            ).then(res => {
                this.images = res.data.images;
            });
        },
        resetform: function() {
            this.search = "";
        },
        updateUrl() {
            let qp = new URLSearchParams();
            if(this.search !== '') {
                qp.set('q', this.search);
            } else {
                qp.set("q", "");
            }
            history.replaceState(null, null, "?"+qp.toString());
        }
    },
    watch: {
        search() {
            this.updateUrl();
        }
    },
});
app.mount('#memes');
