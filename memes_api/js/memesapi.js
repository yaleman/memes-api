var sprintf = new Vue({
    el: '#memes',
    data: {
        images : []
    },
    created () {
        this.getImages();
    },
    watch: {
    },
    methods: {

        getImages: function() {
            axios.get(
                "/allimages",
            ).then(res => {
                this.images = res.data.images;
            });
        }
    },
  })

