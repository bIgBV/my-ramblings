function postLoader () {	
	$.ajax({
		url: '/blog.json',
		dataType: "json"
	}).success(function (data) {
		$('#insert-posts').append(JSON.stringify(data, null, " ").escapeSpecialCharecters());
	});
}

String.prototype.escapeSpecialCharecters = function() {
	return this.replace(/\\n/g, "\\n")
						.replace(/\\'/g, "\\'")
						.replace(/\\"/g, '\\"')
						.replace(/\\&/g, "\\&")
						.replace(/\\r/g, "\\r")
						.replace(/\\t/g, "\\t")
						.replace(/\\b/g, "\\b")
						.replace(/\\f/g, "\\f")
						.replace(/</g, "\&lt;")
						.replace(/>/g, "\&gt;")
};
