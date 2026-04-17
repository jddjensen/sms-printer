namespace SmsPrinter.Models;

public record SmsMessage(string From, string Body, string Time, string Status);
public record PrintingStateDto(bool Enabled);
