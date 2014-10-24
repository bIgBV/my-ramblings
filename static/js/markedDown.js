var markedDown = function () {
	$("textarea[name='content']").on("keyup", function() {
      var value = $(this).val();
      var converter = new Showdown.converter();
      var convertedHtml = converter.makeHtml(value);
      //document.write(convertedHtml);
      $("div[class='preview']").html(convertedHtml);
      $("div[class='length']").html(value.countWords());
    });
    String.prototype.countWords = function(){
 		 return this.split(/\s+\b/).length;
	}
}