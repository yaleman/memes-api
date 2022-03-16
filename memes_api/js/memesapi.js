const imagesPerPage = 15;
const buttonHighlightTime = 1000;

const app = Vue.createApp({
    components: {
      paginate: VuejsPaginateNext,
    },
    delimiters: ['|', '|'], // because we use jinja2 for templating

    data: function(){
        return {
        images : [],
        search: '',
        currentPage: 1, // default to the first page
        button_md: false,
        button_copy: false,
        }
    },
    created () {
        // parse the URL and set search and pagination
        let qp = new URLSearchParams(window.location.search);
        if (qp.get("q") != "" && qp.get("q") != null ) {
            this.search = qp.get("q");
        }
        if (qp.get("p") != "" && qp.get("p") != null ) {
            this.currentPage = Number(qp.get("p"));
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
        paginatedImages() {
            let start = (this.currentPage-1) * imagesPerPage;
            let end =   ((this.currentPage-1) * imagesPerPage) + imagesPerPage
            return this.filteredImages.slice(start, end);
        },
        count_filteredImages() {
            return this.filteredImages.length;
        },
        totalImages() {
            return this.images.length;
        },
        pageCount() {
            let addpage = 0;
            if (this.filteredImages.length % imagesPerPage != 0) {
                addpage = 1;
            }
            return (Math.ceil(this.filteredImages.length / imagesPerPage,0));
        }
    },
    methods: {
        clickCallback: function(pageNum) {
            this.currentPage = pageNum;
            this.updateUrl();
        },
        getImages: function() {
            axios.get(
                "/allimages",
            ).then(res => {
                this.images = res.data.images;
            });
        },
        updateUrl() {
            let qp = new URLSearchParams();
            if(this.search !== '') {
                qp.set('q', this.search);
            } else {
                qp.set("q", "");
            }
            if(this.currentPage > 0) {
                qp.set('p', this.currentPage);
            } else {
                qp.set("p", "");
            }
            history.replaceState(null, null, "?"+qp.toString());
        },
        copy_direct() {
            /* clipboard copy example from https://www.w3schools.com/howto/howto_js_copy_clipboard.asp */
            this.button_copy = true;
            this.$refs.direct_link.focus();

            /* Select the text field */
            this.$refs.direct_link.select();
            this.$refs.direct_link.setSelectionRange(0, 99999); /* For mobile devices */

            /* Copy the text inside the text field */
            navigator.clipboard.writeText(this.$refs.direct_link.value);
            this.$refs.md_link.setSelectionRange(0, 0); /* For mobile devices */

            setTimeout(() => {
                this.button_copy = false;
            }, buttonHighlightTime);
        },
        copy_md() {
            /* clipboard copy example from https://www.w3schools.com/howto/howto_js_copy_clipboard.asp */
            this.button_md = true;
            this.$refs.md_link.focus();

            /* Select the text field */
            this.$refs.md_link.select();
            this.$refs.md_link.setSelectionRange(0, 99999); /* For mobile devices */

            /* Copy the text inside the text field */
            navigator.clipboard.writeText(this.$refs.md_link.value);
            this.$refs.md_link.setSelectionRange(0, 0); /* For mobile devices */

            setTimeout(() => {
                this.button_md = false;
            }, buttonHighlightTime);
        }

    },
    watch: {
        search() {
            if (this.currentPage > this.pageCount) {
                console.log("Setting page to 1");
                this.currentPage = 1;
            }
            this.updateUrl();
        }
    },
});


app.mount('#memes');

