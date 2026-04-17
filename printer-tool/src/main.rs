#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use chrono::Local;
use eframe::egui;

#[cfg(windows)]
mod printer {
    use windows::core::{Error, Result, PCWSTR, PWSTR};
    use windows::Win32::Foundation::HANDLE;
    use windows::Win32::Graphics::Printing::{
        ClosePrinter, EndDocPrinter, EndPagePrinter, OpenPrinterW, StartDocPrinterW,
        StartPagePrinter, WritePrinter, DOC_INFO_1W,
    };

    pub fn print_raw(printer_name: &str, data: &[u8], job: &str) -> Result<()> {
        let printer_wide: Vec<u16> =
            printer_name.encode_utf16().chain(std::iter::once(0)).collect();
        let mut job_wide: Vec<u16> = job.encode_utf16().chain(std::iter::once(0)).collect();
        let mut datatype_wide: Vec<u16> =
            "RAW".encode_utf16().chain(std::iter::once(0)).collect();

        unsafe {
            let mut hprinter: HANDLE = HANDLE::default();
            OpenPrinterW(PCWSTR(printer_wide.as_ptr()), &mut hprinter, None)?;

            let doc_info = DOC_INFO_1W {
                pDocName: PWSTR(job_wide.as_mut_ptr()),
                pOutputFile: PWSTR::null(),
                pDatatype: PWSTR(datatype_wide.as_mut_ptr()),
            };

            let job_id = StartDocPrinterW(hprinter, 1, &doc_info as *const _ as *const u8);
            if job_id == 0 {
                let err = Error::from_win32();
                let _ = ClosePrinter(hprinter);
                return Err(err);
            }

            if let Err(e) = StartPagePrinter(hprinter) {
                let _ = EndDocPrinter(hprinter);
                let _ = ClosePrinter(hprinter);
                return Err(e);
            }

            let mut written: u32 = 0;
            if let Err(e) = WritePrinter(
                hprinter,
                data.as_ptr() as *const core::ffi::c_void,
                data.len() as u32,
                &mut written,
            ) {
                let _ = EndPagePrinter(hprinter);
                let _ = EndDocPrinter(hprinter);
                let _ = ClosePrinter(hprinter);
                return Err(e);
            }

            EndPagePrinter(hprinter)?;
            EndDocPrinter(hprinter)?;
            ClosePrinter(hprinter)?;
        }

        Ok(())
    }
}

fn build_sms_receipt(from: &str, body: &str) -> Vec<u8> {
    let ts = Local::now().format("%Y-%m-%d %H:%M:%S");
    let sep = "-".repeat(32);
    let text = format!(
        "\nNEW MESSAGE\n{sep}\nFrom: {from}\nTime: {ts}\n{sep}\n\n{body}\n\n\n\n\n\n\n"
    );
    let mut out = text.into_bytes();
    out.extend_from_slice(&[0x1d, 0x56, 0x41, 0x05]); // GS V A 5 — partial cut w/ feed
    out
}

fn build_plain(text: &str) -> Vec<u8> {
    let mut out = format!("\n{text}\n\n\n\n\n\n").into_bytes();
    out.extend_from_slice(&[0x1d, 0x56, 0x41, 0x05]);
    out
}

struct App {
    printer_name: String,
    from: String,
    message: String,
    status: String,
}

impl Default for App {
    fn default() -> Self {
        Self {
            printer_name: "POS-80".to_string(),
            from: "Desktop".to_string(),
            message: String::new(),
            status: "Ready.".to_string(),
        }
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading("SMS Printer — Desktop");
            ui.add_space(8.0);

            egui::Grid::new("fields").num_columns(2).show(ui, |ui| {
                ui.label("Printer:");
                ui.text_edit_singleline(&mut self.printer_name);
                ui.end_row();

                ui.label("From:");
                ui.text_edit_singleline(&mut self.from);
                ui.end_row();
            });

            ui.add_space(8.0);
            ui.label("Message:");
            ui.add(
                egui::TextEdit::multiline(&mut self.message)
                    .desired_rows(8)
                    .desired_width(f32::INFINITY),
            );

            ui.add_space(8.0);
            ui.horizontal(|ui| {
                if ui.button("Print as SMS").clicked() {
                    let payload = build_sms_receipt(&self.from, &self.message);
                    self.status = match send(&self.printer_name, &payload, "SMS") {
                        Ok(()) => "Printed SMS receipt.".into(),
                        Err(e) => format!("Error: {e}"),
                    };
                }

                if ui.button("Test receipt").clicked() {
                    let payload = build_plain("*** Printer Test OK ***");
                    self.status = match send(&self.printer_name, &payload, "Test") {
                        Ok(()) => "Sent test receipt.".into(),
                        Err(e) => format!("Error: {e}"),
                    };
                }

                if ui.button("Cut paper").clicked() {
                    let payload: Vec<u8> = b"\n\n\n\n\n\n\x1d\x56\x41\x05".to_vec();
                    self.status = match send(&self.printer_name, &payload, "Cut") {
                        Ok(()) => "Paper cut.".into(),
                        Err(e) => format!("Error: {e}"),
                    };
                }
            });

            ui.add_space(8.0);
            ui.separator();
            ui.label(&self.status);
        });
    }
}

#[cfg(windows)]
fn send(name: &str, data: &[u8], job: &str) -> Result<(), String> {
    printer::print_raw(name, data, job).map_err(|e| e.to_string())
}

#[cfg(not(windows))]
fn send(_name: &str, _data: &[u8], _job: &str) -> Result<(), String> {
    Err("Printing is only supported on Windows.".into())
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([560.0, 480.0]),
        ..Default::default()
    };
    eframe::run_native(
        "SMS Printer — Desktop",
        options,
        Box::new(|_cc| Ok(Box::<App>::default())),
    )
}
