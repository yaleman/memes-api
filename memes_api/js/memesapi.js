var memes = new Vue({
    delimiters: ['|', '|'], // because we use jinja2 for templating
    el: '#memes',
    data: {
        images : [],
        search_box: '',
    },
    created () {
        this.getImages();
    },
    computed: {
        filteredImages() {
            return this.images.filter(image =>{
                const searchTerm = this.search_box.toLowerCase();
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
            this.search_box = "";
        }
    },
  })

